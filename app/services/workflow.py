"""BE-05/BE-09: атомарная первичная и повторная подача заявки.

Триггер alfa.application_audit автоматически добавляет событие при каждом UPDATE.
Не вставляйте application_events вручную: иначе журнал будет продублирован.
"""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import Connection, text

from ..core.errors import ApiProblem
from ..core.security import Actor
from ..repository import actor_company
from .applications import _get_raw
from .bank_turnover import get_bank_history_metrics

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    'DRAFT': frozenset({'SUBMITTED'}),
    'SUBMITTED': frozenset({'CHECKING'}),
    'CHECKING': frozenset({'NEED_INFO', 'UNDER_REVIEW', 'OFFERED', 'REJECTED'}),
    'NEED_INFO': frozenset({'CHECKING'}),
    'UNDER_REVIEW': frozenset({'NEED_INFO', 'OFFERED', 'REJECTED'}),
    'OFFERED': frozenset({'ACCEPTED', 'CANCELLED'}),
    'ACCEPTED': frozenset({'SIGNED'}),
    'SIGNED': frozenset({'DISBURSED'}),
    'DISBURSED': frozenset(),
    'REJECTED': frozenset(),
    'CANCELLED': frozenset(),
}
RULE_VERSION = 'rules-v2-bank'


def ensure_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION',
                         f'Переход из {current} в {target} запрещён')


def _hash_request(application_id: UUID, version: int,
                  clarification: str | None = None) -> str:
    request = {'application_id': str(application_id), 'version': version}
    if clarification is not None:
        request['clarification'] = clarification
    canonical = json.dumps(request, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _snapshot(row) -> dict:
    return {
        'company_id': str(row['company_id']),
        'requested_amount': str(row['amount']),
        'term_months': row['term'],
        'monthly_revenue': str(row['revenue']),
        'operating_expenses': str(row['expenses']),
        'existing_debt_payments': str(row['debt_payments']),
        'business_age_months': row['age_months'],
        'cash_reserve': str(row['cash_reserve']) if row['cash_reserve'] is not None else None,
        'document_confirmed': row['document_confirmed'],
    }


def submit_one(conn: Connection, actor: Actor, application_id: UUID, version: int,
               idempotency_key: str | None = None,
               clarification: str | None = None) -> dict:
    '''Первичная подача DRAFT или повторная подача NEED_INFO.
    DRAFT -> SUBMITTED -> CHECKING (2 события/версии).
    NEED_INFO -> CHECKING (1 событие/версия), обязательно с новыми данными
    и/или пояснением. Каждый submit создаёт новый evaluation_run.
    '''
    if idempotency_key is not None:
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))'),
                     {'scope': f'{actor.id}:SUBMIT:{idempotency_key}'})
    actor_company(conn, actor.id)
    row = _get_raw(conn, actor, application_id, lock=True)
    request_hash = _hash_request(application_id, version, clarification)
    if idempotency_key is not None:
        previous_key = conn.execute(text('''SELECT request_hash,response_body
            FROM alfa.idempotency_keys
            WHERE user_id=:user AND operation='SUBMIT' AND key=:key'''),
            {'user': actor.id, 'key': idempotency_key}).mappings().first()
        if previous_key:
            if previous_key['request_hash'] != request_hash:
                raise ApiProblem(409, 'IDEMPOTENCY_CONFLICT',
                                 'Этот Idempotency-Key уже применён к другому запросу')
            if previous_key['response_body'] is None:
                raise ApiProblem(409, 'REQUEST_IN_PROGRESS', 'Запрос ещё обрабатывается')
            return previous_key['response_body']
    if row['version'] != version:
        raise ApiProblem(409, 'VERSION_CONFLICT',
                         'Версия заявки устарела. Обновите карточку заявки')
    state = row['status']
    if state == 'DRAFT':
        ensure_transition('DRAFT', 'SUBMITTED')
    elif state == 'NEED_INFO':
        ensure_transition('NEED_INFO', 'CHECKING')
    else:
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION',
                         'Отправка доступна только из DRAFT или NEED_INFO')

    input_snapshot = _snapshot(row)
    # Банковскую историю сохраняем в момент подачи заявки.
    input_snapshot['bank_history'] = get_bank_history_metrics(
        conn, row['company_id']
    )
    if clarification is not None:
        input_snapshot['client_clarification'] = clarification
    if state == 'NEED_INFO':
        prior_run = conn.execute(text('''SELECT input_snapshot
            FROM alfa.evaluation_runs WHERE application_id=:app
            ORDER BY submission_version DESC LIMIT 1'''),
            {'app': application_id}).mappings().first()
        if prior_run is None:
            raise ApiProblem(409, 'NO_EVALUATION',
                             'Не найден предыдущий цикл проверки заявки')
        if prior_run['input_snapshot'] == input_snapshot:
            raise ApiProblem(409, 'NO_NEW_INFORMATION',
                             'Сначала уточните данные анкеты через PATCH или добавьте пояснение')
    product = conn.execute(text('''SELECT code,min_amount,max_amount,min_term,max_term,demo_rate
        FROM alfa.credit_products WHERE id=:product'''),
        {'product': row['product_id']}).mappings().first()
    if not product:
        raise ApiProblem(409, 'PRODUCT_NOT_FOUND', 'Продукт заявки больше не найден')
    product_snapshot = {
        'code': product['code'],
        'min_amount': str(product['min_amount']),
        'max_amount': str(product['max_amount']),
        'min_term': product['min_term'],
        'max_term': product['max_term'],
        'demo_rate': str(product['demo_rate']),
    }
    conn.execute(text("SELECT set_config('app.actor_id', :actor, true)"),
                 {'actor': str(actor.id)})
    if state == 'DRAFT':
        submitted = conn.execute(text('''UPDATE alfa.loan_applications
            SET status='SUBMITTED'
            WHERE id=:app AND company_id=:company AND version=:version AND status='DRAFT'
            RETURNING version'''),
            {'app': application_id, 'company': actor.company_id, 'version': version}).mappings().first()
        if submitted is None:
            raise ApiProblem(409, 'VERSION_CONFLICT', 'Заявка уже изменена')
        submission_version = submitted['version']
    else:
        checking = conn.execute(text('''UPDATE alfa.loan_applications
            SET status='CHECKING'
            WHERE id=:app AND company_id=:company AND version=:version AND status='NEED_INFO'
            RETURNING version'''),
            {'app': application_id, 'company': actor.company_id, 'version': version}).mappings().first()
        if checking is None:
            raise ApiProblem(409, 'VERSION_CONFLICT', 'Заявка уже изменена')
        submission_version = checking['version']
    run = conn.execute(text('''INSERT INTO alfa.evaluation_runs
        (application_id,financial_profile_id,submission_version,rule_version,input_snapshot,product_snapshot)
        VALUES (:app,:profile,:submitted_version,:rule_version,
                CAST(:input_snapshot AS jsonb),CAST(:product_snapshot AS jsonb))
        RETURNING id'''), {
        'app': application_id,
        'profile': row['financial_profile_id'],
        'submitted_version': submission_version,
        'rule_version': RULE_VERSION,
        'input_snapshot': json.dumps(input_snapshot, ensure_ascii=False),
        'product_snapshot': json.dumps(product_snapshot, ensure_ascii=False),
    }).mappings().first()
    if run is None:
        raise RuntimeError('Не удалось создать цикл проверки')
    if state == 'DRAFT':
        ensure_transition('SUBMITTED', 'CHECKING')
        checking = conn.execute(text('''UPDATE alfa.loan_applications
            SET status='CHECKING'
            WHERE id=:app AND company_id=:company AND version=:version AND status='SUBMITTED'
            RETURNING version'''), {
            'app': application_id, 'company': actor.company_id,
            'version': submitted['version'],
        }).mappings().first()
        if checking is None:
            raise ApiProblem(409, 'VERSION_CONFLICT', 'Заявка изменилась во время подачи')
    output = {
        'id': str(application_id), 'status': 'CHECKING',
        'version': checking['version'], 'evaluation_run_id': str(run['id']),
    }
    if idempotency_key is not None:
        conn.execute(text('''INSERT INTO alfa.idempotency_keys
            (user_id,operation,key,request_hash,application_id,response_code,response_body,completed_at)
            VALUES (:user,'SUBMIT',:key,:request_hash,:app,200,CAST(:body AS jsonb),clock_timestamp())'''), {
            'user': actor.id, 'key': idempotency_key, 'request_hash': request_hash,
            'app': application_id,
            'body': json.dumps(output, ensure_ascii=False),
        })
    return output
