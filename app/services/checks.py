"""BE-06: mock-проверки ФНС и БКИ с записью в неизменяемую историю.

Одна транзакция: блокировка заявки -> получение последнего evaluation_run ->
чтение синтетического профиля -> INSERT двух проверок -> выдача результатов.
SQL-схема создаёт UNIQUE(run_id,source) и запрещает UPDATE/DELETE истории.
"""
from __future__ import annotations

import json
from uuid import UUID
from sqlalchemy import Connection, text

from ..core.errors import ApiProblem
from ..core.security import Actor
from ..integrations.fns_mock import check_registry
from ..integrations.bki_mock import check_credit_history


# Порядок фиксирован для UI и воспроизводимости тестов.
CHECK_ORDER = ('FNS', 'BKI')


def _app_and_run(conn: Connection, actor: Actor, app_id: UUID, *, lock: bool):
    if actor.company_id is None or actor.role != 'CLIENT':
        raise ApiProblem(403, 'FORBIDDEN', 'Только клиент может просматривать свою заявку')
    query = '''SELECT id, company_id, status FROM alfa.loan_applications
        WHERE id=:app AND company_id=:company'''
    if lock:
        query += ' FOR UPDATE'
    application = conn.execute(text(query), {
        'app': app_id, 'company': actor.company_id,
    }).mappings().first()
    if not application:
        raise ApiProblem(404, 'NOT_FOUND', 'Заявка не найдена')

    latest = conn.execute(text('''SELECT id FROM alfa.evaluation_runs
        WHERE application_id=:app
        ORDER BY submission_version DESC LIMIT 1'''),
        {'app': app_id}).mappings().first()
    return application, (latest['id'] if latest else None)


def _rows(conn: Connection, run_id: UUID) -> list[dict]:
    rows = conn.execute(text('''SELECT id, run_id, source, result, payload, checked_at
        FROM alfa.verifications WHERE run_id=:run
        ORDER BY CASE source WHEN 'FNS' THEN 0 ELSE 1 END'''),
        {'run': run_id}).mappings().all()
    return [dict(row) for row in rows]


def _summary(app_id: UUID, status: str, run_id: UUID | None, rows: list[dict]) -> dict:
    unique_sources = {item['source'] for item in rows}
    reasons: set[str] = set()
    for item in rows:
        _flag, codes = (check_registry(item['result']) if item['source'] == 'FNS'
                        else check_credit_history(item['result']))
        reasons.update(codes)
    return {
        'application_id': app_id, 'evaluation_run_id': run_id,
        'application_status': status,
        'completed': unique_sources == set(CHECK_ORDER),
        'checks': rows,
        'reason_codes': sorted(reasons),
    }


def get_checks(conn: Connection, actor: Actor, app_id: UUID) -> dict:
    """Чтение не запускает mock; DRAFT возвращает пустой список."""
    application, run_id = _app_and_run(conn, actor, app_id, lock=False)
    return _summary(app_id, application['status'], run_id,
                    _rows(conn, run_id) if run_id is not None else [])


def ensure_checks(conn: Connection, actor: Actor, app_id: UUID) -> dict:
    """Идемпотентно сохранить ФНС/БКИ для последнего run.

    Включая уже отправленные BE-05 заявки. Никогда не меняет статус.
    Повторная обработка не перезаписывает исторические флаги при изменении
    mock_profiles: используется сохранённый результат первой проверки.
    """
    application, run_id = _app_and_run(conn, actor, app_id, lock=True)
    if run_id is None:
        raise ApiProblem(409, 'NOT_SUBMITTED', 'Сначала отправьте заявку на проверку')
    already = _rows(conn, run_id)
    seen = {check['source'] for check in already}
    if seen == set(CHECK_ORDER):
        # Повтор ранее завершённого запроса ничего не пишет даже после того,
        # как заявка перешла из CHECKING к сотруднику банка.
        return _summary(app_id, application['status'], run_id, already)
    if application['status'] != 'CHECKING':
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION',
                         'Новые проверки можно запускать только в статусе CHECKING')

    mock = conn.execute(text('''SELECT registry_flag, credit_history_flag
        FROM alfa.mock_profiles WHERE company_id=:company'''),
        {'company': application['company_id']}).mappings().first()
    fns, _ = check_registry(mock['registry_flag'] if mock else None)
    bki, _ = check_credit_history(mock['credit_history_flag'] if mock else None)
    planned = {'FNS': fns, 'BKI': bki}

    for source in CHECK_ORDER:
        if source in seen:
            continue
        # Мы не выдаём неизвестный результат за успешный: unknown будет
        # маршрутизирован в ручную обработку на этапе BE-07.
        payload = {'provider': f'{source.lower()}_local_mock',
                   'synthetic': True, 'mock_profile_present': mock is not None}
        conn.execute(text('''INSERT INTO alfa.verifications
            (application_id,run_id,source,result,payload)
            VALUES (:app,:run,:source,:result,CAST(:payload AS jsonb))
            ON CONFLICT (run_id,source) DO NOTHING'''), {
            'app': app_id, 'run': run_id, 'source': source,
            'result': planned[source], 'payload': json.dumps(payload),
        })
    return _summary(app_id, application['status'], run_id, _rows(conn, run_id))
