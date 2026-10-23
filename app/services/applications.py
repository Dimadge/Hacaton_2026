"""Черновики поверх существующей SQL-схемы. Доступ — только к своей company_id."""
from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Connection, text
from ..repository import actor_company, create_draft
from ..core.errors import ApiProblem
from ..core.security import Actor
from ..schemas.application import ApplicationCreate, ApplicationPatch


def _product(conn: Connection, code: str):
    product = conn.execute(text("""SELECT id,code,min_amount,max_amount,min_term,max_term
        FROM alfa.credit_products WHERE code=:code AND active=true"""), {'code': code}).mappings().first()
    if product is None:
        raise ApiProblem(422, 'PRODUCT_NOT_FOUND', 'Кредитный продукт не найден')
    return product


def _check_tariff(product, amount: Decimal, term: int):
    if not (product['min_amount'] <= amount <= product['max_amount'] and
            product['min_term'] <= term <= product['max_term']):
        raise ApiProblem(422, 'PRODUCT_LIMIT', 'Сумма или срок выходят за границы продукта', {
            'min_amount': str(product['min_amount']), 'max_amount': str(product['max_amount']),
            'min_term': product['min_term'], 'max_term': product['max_term']})


def _get_raw(conn: Connection, actor: Actor, app_id: UUID, lock: bool = False):
    query = """SELECT a.id,a.company_id,p.code AS product_code,a.product_id,a.amount,
           a.term,a.purpose,a.status,a.version,a.created_at,
           f.revenue,f.expenses,f.debt_payments,f.age_months,f.cash_reserve,
           f.document_confirmed,f.revision,f.id AS financial_profile_id
           FROM alfa.loan_applications a
           JOIN alfa.credit_products p ON p.id=a.product_id
           JOIN LATERAL (
               SELECT * FROM alfa.financial_profiles WHERE application_id=a.id
               ORDER BY revision DESC LIMIT 1
           ) f ON true
           WHERE a.id=:id AND a.company_id=:company"""
    # Postgres FOR UPDATE OF a blocks concurrent edits to same application.
    if lock:
        query += ' FOR UPDATE OF a'
    row = conn.execute(text(query), {'id': app_id, 'company': actor.company_id}).mappings().first()
    if row is None:
        # Для чужой заявки ответ такой же, как для несуществующей.
        raise ApiProblem(404, 'NOT_FOUND', 'Заявка не найдена')
    return row


def _public(row):
    return {
        'id': row['id'], 'company_id': row['company_id'],
        'product_code': row['product_code'], 'purpose': row['purpose'],
        'requested_amount': row['amount'], 'term_months': row['term'],
        'status': row['status'], 'version': row['version'], 'created_at': row['created_at'],
        'financials': {
            'monthly_revenue': row['revenue'], 'operating_expenses': row['expenses'],
            'existing_debt_payments': row['debt_payments'],
            'business_age_months': row['age_months'], 'cash_reserve': row['cash_reserve'],
            'document_confirmed': row['document_confirmed'],
        },
    }


def get_one(conn: Connection, actor: Actor, app_id: UUID):
    actor_company(conn, actor.id)
    return _public(_get_raw(conn, actor, app_id))


def list_mine(conn: Connection, actor: Actor):
    actor_company(conn, actor.id)
    rows = conn.execute(text("""SELECT a.id,a.status,p.code AS product_code,
        a.amount AS requested_amount,a.term AS term_months,a.version,a.created_at
        FROM alfa.loan_applications a JOIN alfa.credit_products p ON a.product_id=p.id
        WHERE a.company_id=:company ORDER BY a.created_at DESC,a.id DESC"""),
        {'company': actor.company_id}).mappings().all()
    return [dict(r) for r in rows]


def create_one(conn: Connection, actor: Actor, data: ApplicationCreate):
    product = _product(conn, data.product_code)
    _check_tariff(product, data.requested_amount, data.term_months)
    f = data.financials
    app_id, _ = create_draft(
        conn, actor_id=actor.id, product_code=product['code'], amount=data.requested_amount,
        term=data.term_months, purpose=data.purpose.strip(),
        revenue=f.monthly_revenue, expenses=f.operating_expenses,
        debt_payments=f.existing_debt_payments, age_months=f.business_age_months,
        cash_reserve=f.cash_reserve, document_confirmed=f.document_confirmed,
    )
    return _public(_get_raw(conn, actor, app_id))


def update_one(conn: Connection, actor: Actor, app_id: UUID, data: ApplicationPatch):
    actor_company(conn, actor.id)
    current = _get_raw(conn, actor, app_id, lock=True)
    if current['status'] not in ('DRAFT', 'NEED_INFO'):
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION', 'Эту заявку уже нельзя редактировать')
    if current['version'] != data.version:
        raise ApiProblem(409, 'VERSION_CONFLICT', 'Заявка уже изменена. Обновите страницу')
    amount = data.requested_amount if data.requested_amount is not None else current['amount']
    term = data.term_months if data.term_months is not None else current['term']
    product = _product(conn, current['product_code'])
    _check_tariff(product, amount, term)
    purpose = data.purpose.strip() if data.purpose is not None else current['purpose']
    conn.execute(text("""UPDATE alfa.loan_applications
        SET amount=:amount,term=:term,purpose=:purpose
        WHERE id=:id AND company_id=:company AND version=:version"""), {
        'amount': amount, 'term': term, 'purpose': purpose,
        'id': app_id, 'company': actor.company_id, 'version': data.version,
    })
    if data.financials is not None:
        changed = data.financials.model_dump(exclude_unset=True)
        mapping = {
            'monthly_revenue': 'revenue', 'operating_expenses': 'expenses',
            'existing_debt_payments': 'debt_payments', 'business_age_months': 'age_months',
            'cash_reserve': 'cash_reserve', 'document_confirmed': 'document_confirmed',
        }
        values = {column: current[column] for column in mapping.values()}
        for api_field, value in changed.items():
            if value is None and api_field != 'cash_reserve':
                raise ApiProblem(422, 'VALIDATION_ERROR', f'{api_field} не может быть null')
            values[mapping[api_field]] = value
        conn.execute(text("""INSERT INTO alfa.financial_profiles
           (application_id,revision,revenue,expenses,debt_payments,age_months,cash_reserve,document_confirmed)
           VALUES (:app,:revision,:revenue,:expenses,:debt_payments,:age_months,:cash_reserve,:document_confirmed)"""),
           {'app': app_id, 'revision': current['revision']+1, **values})
    return _public(_get_raw(conn, actor, app_id))


def events_for(conn: Connection, actor: Actor, app_id: UUID):
    actor_company(conn, actor.id)
    _get_raw(conn, actor, app_id)
    rows = conn.execute(text("""SELECT id,action,from_status,to_status,application_version,at
        FROM alfa.application_events WHERE application_id=:app ORDER BY id"""),
        {'app': app_id}).mappings().all()
    return [dict(r) for r in rows]
