"""BE-07: кредитные решения, банк и предложения на имеющейся alfa.* БД.

Правила:
* один запрос = одна SQLAlchemy-транзакция через get_connection;
* loan_applications блокируется FOR UPDATE до принятия решений;
* триггер alfa.application_audit пишет события: вручную их НЕ дублировать;
* никогда не генерируем положительный скоринг/офферы без валидной оценки DS;
* авто-решение не может быть инициировано CLIENT;
* UNDER_REVIEW вручную обрабатывает только BANK_EMPLOYEE.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from sqlalchemy import Connection, text

from ..core.errors import ApiProblem
from ..core.security import Actor
from ..services.applications import _get_raw
from .workflow import ensure_transition
from .decision_policy import decide_preliminary


MONEY_CENT = Decimal('0.01')


def annuity(amount: Decimal, months: int, annual_rate: Decimal) -> Decimal:
    """Аннуитет для технической валидации предложения, не кредитный скоринг."""
    if amount <= 0 or months <= 0 or not 0 <= annual_rate <= 1:
        raise ValueError('Неверные параметры кредита')
    r = annual_rate / Decimal(12)
    if r == 0:
        return (amount / Decimal(months)).quantize(MONEY_CENT, rounding=ROUND_HALF_UP)
    result = amount * r / (Decimal(1) - (Decimal(1) + r) ** (-months))
    return result.quantize(MONEY_CENT, rounding=ROUND_HALF_UP)


def _application_bank(conn: Connection, app_id: UUID, *, lock: bool = False) -> dict:
    sql = '''SELECT a.id,a.status,a.version,a.company_id,c.name AS company_name,
       a.amount AS requested_amount,a.term AS term_months,a.created_at,
       p.code AS product_code, f.document_confirmed
       FROM alfa.loan_applications a
       JOIN alfa.companies c ON c.id=a.company_id
       JOIN alfa.credit_products p ON p.id=a.product_id
       JOIN LATERAL (SELECT document_confirmed FROM alfa.financial_profiles
           WHERE application_id=a.id ORDER BY revision DESC LIMIT 1) f ON true
       WHERE a.id=:app'''
    if lock:
        sql += ' FOR UPDATE OF a'
    row = conn.execute(text(sql), {'app': app_id}).mappings().first()
    if not row:
        raise ApiProblem(404, 'NOT_FOUND', 'Заявка не найдена')
    return dict(row)


def _latest_run(conn: Connection, app_id: UUID) -> dict | None:
    row = conn.execute(text('''SELECT id,input_snapshot,product_snapshot,rule_version
        FROM alfa.evaluation_runs WHERE application_id=:app
        ORDER BY submission_version DESC LIMIT 1'''), {'app': app_id}).mappings().first()
    return dict(row) if row else None


def _checks_for_run(conn: Connection, run_id: UUID) -> dict[str, str]:
    rows = conn.execute(text('''SELECT source,result FROM alfa.verifications
        WHERE run_id=:run'''), {'run': run_id}).mappings().all()
    return {r['source']: r['result'] for r in rows}


def _scoring_for_run(conn: Connection, run_id: UUID) -> dict | None:
    row = conn.execute(text('''SELECT score,risk,max_new_payment
        FROM alfa.scoring_results WHERE run_id=:run'''), {'run': run_id}).mappings().first()
    return dict(row) if row else None


def _change_status(conn: Connection, actor_id: UUID | None, app_id: UUID,
                   version: int, old: str, new: str) -> int:
    ensure_transition(old, new)
    conn.execute(text("SELECT set_config('app.actor_id', :actor, true)"),
                 {'actor': str(actor_id) if actor_id else ''})
    updated = conn.execute(text('''UPDATE alfa.loan_applications
        SET status=CAST(:target AS alfa.application_status)
        WHERE id=:app AND version=:version AND status=CAST(:previous AS alfa.application_status)
        RETURNING version'''),
        {'target': new, 'previous': old, 'app': app_id, 'version': version}).mappings().first()
    if updated is None:
        raise ApiProblem(409, 'VERSION_CONFLICT', 'Заявка уже изменилась')
    return updated['version']


def _write_decision(conn: Connection, app_id: UUID, run_id: UUID,
                    kind: str, reasons: tuple[str, ...] | list[str],
                    actor_id: UUID | None, comment: str | None = None) -> UUID:
    # row lock приложения сериализует все решения на один run.
    next_seq = conn.execute(text('''SELECT COALESCE(MAX(sequence_no),0)+1
        FROM alfa.credit_decisions WHERE run_id=:run'''), {'run': run_id}).scalar_one()
    decision_id = conn.execute(text('''INSERT INTO alfa.credit_decisions
        (application_id,run_id,sequence_no,decision_type,created_by,comment)
        VALUES (:app,:run,:seq,CAST(:kind AS alfa.decision_kind),:actor,:comment)
        RETURNING id'''), {'app': app_id, 'run': run_id, 'seq': next_seq, 'kind': kind,
                            'actor': actor_id, 'comment': comment}).scalar_one()
    for code in reasons:
        valid = conn.execute(text('''SELECT 1 FROM alfa.reason_codes WHERE code=:code'''),
                             {'code': code}).scalar_one_or_none()
        if valid is None:
            raise ApiProblem(422, 'UNKNOWN_REASON_CODE', f'Неизвестный код причины: {code}')
        conn.execute(text('''INSERT INTO alfa.decision_reasons(decision_id,reason_code)
            VALUES (:decision,:code)'''), {'decision': decision_id, 'code': code})
    return decision_id


def bank_queue(conn: Connection) -> list[dict]:
    rows = conn.execute(text('''SELECT a.id,a.company_id,c.name AS company_name,
        a.status,p.code AS product_code,a.amount AS requested_amount,
        a.term AS term_months,a.version,a.created_at
        FROM alfa.loan_applications a
        JOIN alfa.companies c ON c.id=a.company_id
        JOIN alfa.credit_products p ON p.id=a.product_id
        WHERE a.status IN ('UNDER_REVIEW','CHECKING','NEED_INFO')
        ORDER BY a.updated_at DESC,a.id DESC LIMIT 100''')).mappings().all()
    return [dict(row) for row in rows]


def bank_application(conn: Connection, app_id: UUID) -> dict:
    app = _application_bank(conn, app_id)
    run = _latest_run(conn, app_id)
    checks = _checks_for_run(conn, run['id']) if run else {}
    return {**app, 'evaluation_run_id': run['id'] if run else None,
            'verification_results': checks,
            'scoring_ready': bool(run and _scoring_for_run(conn, run['id'])),
            'client_clarification': run['input_snapshot'].get('client_clarification') if run else None}


def bank_evaluate(conn: Connection, actor: Actor, app_id: UUID) -> dict:
    """Запуск policy после ФНС/БКИ, пока вручную (не ломает BE-06 submit).

    Проходит без DS только отрицательные или спорные случаи. При active/good
    без DS возвращает SCORING_PENDING, заявка остаётся CHECKING.
    """
    app = _application_bank(conn, app_id, lock=True)
    if app['status'] != 'CHECKING':
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION',
                         'Автоматическая оценка доступна только в CHECKING')
    run = _latest_run(conn, app_id)
    if not run:
        raise ApiProblem(409, 'NO_EVALUATION', 'Цикл проверки не найден')
    flags = _checks_for_run(conn, run['id'])
    if set(flags) != {'FNS','BKI'}:
        raise ApiProblem(409, 'VERIFICATIONS_INCOMPLETE', 'Сначала завершите ФНС и БКИ')
    scoring = _scoring_for_run(conn, run['id'])
    docs = run['input_snapshot'].get('document_confirmed', False)
    outcome = decide_preliminary(fns=flags['FNS'], bki=flags['BKI'],
                                 document_confirmed=bool(docs),
                                 score=scoring['score'] if scoring else None,
                                 risk=scoring['risk'] if scoring else None)
    if outcome.target_status is None:
        return {'application_id': app_id, 'status': app['status'], 'version': app['version'],
                'decision_type': None, 'reason_codes': list(outcome.reason_codes),
                'next_step': outcome.next_step}
    _write_decision(conn, app_id, run['id'], outcome.decision_type,
                    outcome.reason_codes, actor_id=None,
                    comment='Автоматическое учебное правило BE-07; синтетические данные')
    version = _change_status(conn, actor_id=None, app_id=app_id,
                             version=app['version'], old='CHECKING',
                             new=outcome.target_status)
    return {'application_id': app_id, 'status': outcome.target_status,
            'version': version, 'decision_type': outcome.decision_type,
            'reason_codes': list(outcome.reason_codes), 'next_step': outcome.next_step}


def manual_decision(conn: Connection, actor: Actor, app_id: UUID, data) -> dict:
    app = _application_bank(conn, app_id, lock=True)
    if app['version'] != data.version:
        raise ApiProblem(409, 'VERSION_CONFLICT', 'Версия заявки устарела')
    if app['status'] != 'UNDER_REVIEW':
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION',
                         'Сотрудник принимает решение только по UNDER_REVIEW')
    run = _latest_run(conn, app_id)
    if not run:
        raise ApiProblem(409, 'NO_EVALUATION', 'Цикл проверки не найден')
    target = {'REQUEST_INFO':'NEED_INFO', 'REJECT':'REJECTED', 'APPROVE':'OFFERED'}[data.action]
    if data.action == 'APPROVE':
        # Условия не могут быть выдуманы: нужен настоящий сохранённый скоринг DS.
        scoring = _scoring_for_run(conn, run['id'])
        if not scoring:
            raise ApiProblem(409, 'SCORING_PENDING',
                             'Одобрение невозможно до получения оценки DS')
        if scoring['risk'] == 'HIGH':
            raise ApiProblem(409, 'HIGH_RISK', 'Модель пометила заявку как высокорисковую')
        product = run['product_snapshot']
        accepted = []
        seen = set()
        for i, offer in enumerate(data.offers, start=1):
            amount, months = offer.amount, offer.term_months
            rate = Decimal(str(product['demo_rate']))
            if (amount < Decimal(str(product['min_amount'])) or
                amount > Decimal(str(product['max_amount'])) or
                months < int(product['min_term']) or months > int(product['max_term'])):
                raise ApiProblem(422, 'PRODUCT_LIMIT', 'Оффер выходит за пределы продукта')
            if (amount, months) in seen:
                raise ApiProblem(422, 'DUPLICATE_OFFERS', 'Повторяющиеся предложения запрещены')
            seen.add((amount, months))
            payment = annuity(amount, months, rate)
            if payment > scoring['max_new_payment']:
                raise ApiProblem(422, 'PAYMENT_OVER_LIMIT',
                                 'Платёж превышает лимит из оценки DS')
            accepted.append((i, amount, months, rate, payment))
    else:
        accepted = []
    kind = data.action  # совпадает со значениями decision_kind в БД
    decision_id = _write_decision(conn, app_id, run['id'], kind, data.reason_codes,
                                  actor_id=actor.id, comment=data.comment)
    for rank, amount, months, rate, monthly_payment in accepted:
        conn.execute(text('''INSERT INTO alfa.credit_offers
            (application_id,decision_id,amount,term,rate,monthly_payment,rank)
            VALUES (:app,:decision,:amount,:term,:rate,:payment,:rank)'''),
            {'app': app_id, 'decision': decision_id, 'amount': amount,
             'term': months, 'rate': rate, 'payment': monthly_payment, 'rank': rank})
    version = _change_status(conn, actor_id=actor.id, app_id=app_id,
                             version=app['version'], old='UNDER_REVIEW', new=target)
    return {'application_id': app_id, 'status': target, 'version': version,
            'decision_type': kind, 'reason_codes': data.reason_codes,
            'next_step': 'CLIENT_OFFER' if target == 'OFFERED' else
                         ('CLIENT_INFO' if target == 'NEED_INFO' else 'FINAL')}


def get_offers(conn: Connection, actor: Actor, app_id: UUID) -> dict:
    # Чтение строго по своей company_id, как во всех client endpoints.
    app = _get_raw(conn, actor, app_id)
    last = conn.execute(text('''SELECT id,decision_type
        FROM alfa.credit_decisions WHERE application_id=:app
          AND run_id=(SELECT id FROM alfa.evaluation_runs WHERE application_id=:app
                      ORDER BY submission_version DESC LIMIT 1)
        ORDER BY created_at DESC,sequence_no DESC LIMIT 1'''), {'app': app_id}).mappings().first()
    if last is None:
        return {'application_id': app_id, 'application_status': app['status'],
                'decision_id': None, 'decision_type': None, 'reason_codes': [], 'offers': []}
    reason_rows = conn.execute(text('''SELECT reason_code FROM alfa.decision_reasons
        WHERE decision_id=:decision ORDER BY reason_code'''),
        {'decision': last['id']}).scalars().all()
    offers = conn.execute(text('''SELECT id,amount,term AS term_months,rate,monthly_payment,rank,
        accepted FROM alfa.credit_offers_with_acceptance
        WHERE decision_id=:decision ORDER BY rank'''),
        {'decision': last['id']}).mappings().all()
    return {'application_id': app_id, 'application_status': app['status'],
            'decision_id': last['id'], 'decision_type': last['decision_type'],
            'reason_codes': list(reason_rows), 'offers': [dict(x) for x in offers]}
