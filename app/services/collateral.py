"""Залог клиента: только заявление предмета. Оценку и статус меняет не этот запрос."""
from uuid import UUID
from sqlalchemy import Connection, text

from ..core.errors import ApiProblem
from ..core.security import Actor
from ..repository import actor_company
from .applications import _get_raw


def _rows(conn: Connection, app_id: UUID) -> list[dict]:
    rows = conn.execute(text("""SELECT id, collateral_type, description, owner_name,
        ownership_type, declared_value, assessed_value, has_encumbrance, status, review_comment
        FROM alfa.application_collateral
        WHERE application_id=:app
        ORDER BY created_at, id"""), {'app': app_id}).mappings().all()
    return [dict(row) for row in rows]


def list_for_client(conn: Connection, actor: Actor, app_id: UUID) -> list[dict]:
    actor_company(conn, actor.id)
    _get_raw(conn, actor, app_id)
    return _rows(conn, app_id)


def add_for_client(conn: Connection, actor: Actor, app_id: UUID, data) -> dict:
    actor_company(conn, actor.id)
    current = _get_raw(conn, actor, app_id, lock=True)
    if current['status'] not in ('DRAFT', 'NEED_INFO'):
        raise ApiProblem(409, 'INVALID_STATE_TRANSITION', 'Залог можно указать только в черновике')
    row = conn.execute(text("""INSERT INTO alfa.application_collateral
        (application_id, collateral_type, description, owner_name, ownership_type,
         declared_value, has_encumbrance)
        VALUES (:app, :kind, :description, :owner, :ownership, :value, :encumbrance)
        RETURNING id, collateral_type, description, owner_name, ownership_type,
                  declared_value, assessed_value, has_encumbrance, status, review_comment"""), {
        'app': app_id, 'kind': data.collateral_type, 'description': data.description,
        'owner': data.owner_name, 'ownership': data.ownership_type,
        'value': data.declared_value, 'encumbrance': data.has_encumbrance,
    }).mappings().one()
    return dict(row)


def list_for_bank(conn: Connection, app_id: UUID) -> list[dict]:
    exists = conn.execute(text('SELECT 1 FROM alfa.loan_applications WHERE id=:app'),
                          {'app': app_id}).first()
    if exists is None:
        raise ApiProblem(404, 'NOT_FOUND', 'Заявка не найдена')
    return _rows(conn, app_id)
