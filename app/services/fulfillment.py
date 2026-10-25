"""BE-08: приём оффера, имитация подписи и выдачи.

Атомарно меняется одна строка заявки; audit-триггер БД создаёт событие.
Ни реальные документы, ни банковские переводы здесь не создаются.
"""
from uuid import UUID
from sqlalchemy import Connection, text

from ..core.errors import ApiProblem
from ..core.security import Actor
from .applications import _get_raw
from .workflow import ensure_transition


def _lock(conn: Connection, actor: Actor, application_id: UUID, version: int, expected: str):
    app = _get_raw(conn, actor, application_id, lock=True)
    # CHECK version FIRST, to distinguish concurrent changes from invalid state.
    if app['version'] != version:
        raise ApiProblem(409, 'VERSION_CONFLICT', 'Версия заявки устарела. Обновите страницу')
    if app['status'] != expected:
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION',
                         f'Операция доступна только из {expected}; сейчас {app["status"]}')
    return app


def _actor_context(conn: Connection, actor: Actor):
    # read by alfa.application_audit and written into application_events
    conn.execute(text("SELECT set_config('app.actor_id', :actor, true)"),
                 {'actor': str(actor.id)})


def _update(conn: Connection, actor: Actor, app_id: UUID, version: int, source: str,
            target: str, offer_id: UUID | None = None) -> dict:
    ensure_transition(source, target)
    _actor_context(conn, actor)
    if offer_id is not None:
        sql = '''UPDATE alfa.loan_applications
                 SET status=CAST(:target AS alfa.application_status),accepted_offer_id=:offer
                 WHERE id=:app AND company_id=:company AND status=CAST(:source AS alfa.application_status)
                   AND version=:version RETURNING version,accepted_offer_id'''
    else:
        sql = '''UPDATE alfa.loan_applications
                 SET status=CAST(:target AS alfa.application_status)
                 WHERE id=:app AND company_id=:company AND status=CAST(:source AS alfa.application_status)
                   AND version=:version RETURNING version,accepted_offer_id'''
    changed = conn.execute(text(sql), {'target': target, 'source': source, 'app': app_id,
        'company': actor.company_id, 'version': version, 'offer': offer_id}).mappings().first()
    if changed is None:
        raise ApiProblem(409, 'VERSION_CONFLICT', 'Заявка уже изменена другим запросом')
    return {'id': app_id, 'status': target, 'version': changed['version'],
            'accepted_offer_id': changed['accepted_offer_id'], 'simulated': True}


def accept_offer(conn: Connection, actor: Actor, app_id: UUID, version: int,
                 offer_id: UUID) -> dict:
    _lock(conn, actor, app_id, version, 'OFFERED')
    # Do not trust a client-supplied offer: it must belong to the most recent
    # decision of the newest evaluation of THIS application.
    offer = conn.execute(text('''SELECT o.id,o.decision_id FROM alfa.credit_offers o
        JOIN alfa.credit_decisions d ON d.id=o.decision_id AND d.application_id=o.application_id
        WHERE o.id=:offer AND o.application_id=:app'''),
        {'offer': offer_id, 'app': app_id}).mappings().first()
    if offer is None:
        raise ApiProblem(404, 'OFFER_NOT_FOUND', 'Предложение не найдено для этой заявки')
    latest = conn.execute(text('''SELECT d.id FROM alfa.credit_decisions d
        WHERE d.application_id=:app AND d.run_id=(SELECT r.id FROM alfa.evaluation_runs r
             WHERE r.application_id=:app ORDER BY r.submission_version DESC LIMIT 1)
        ORDER BY d.created_at DESC,d.sequence_no DESC LIMIT 1'''),
        {'app': app_id}).mappings().first()
    if latest is None or latest['id'] != offer['decision_id']:
        raise ApiProblem(409, 'STALE_OFFER', 'Предложение устарело; получите актуальные условия')
    return _update(conn, actor, app_id, version, 'OFFERED', 'ACCEPTED', offer_id)


def sign_application(conn: Connection, actor: Actor, app_id: UUID, version: int) -> dict:
    _lock(conn, actor, app_id, version, 'ACCEPTED')
    return _update(conn, actor, app_id, version, 'ACCEPTED', 'SIGNED')


def simulate_disbursement(conn: Connection, actor: Actor, app_id: UUID, version: int) -> dict:
    _lock(conn, actor, app_id, version, 'SIGNED')
    return _update(conn, actor, app_id, version, 'SIGNED', 'DISBURSED')


def cancel_offer(conn: Connection, actor: Actor, app_id: UUID, version: int) -> dict:
    _lock(conn, actor, app_id, version, 'OFFERED')
    return _update(conn, actor, app_id, version, 'OFFERED', 'CANCELLED')
