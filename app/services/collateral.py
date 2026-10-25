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


def review_for_bank(
    conn: Connection,
    actor: Actor,
    app_id: UUID,
    collateral_id: UUID,
    data,
) -> dict:
    application_status = conn.execute(
        text("""
            SELECT status
            FROM alfa.loan_applications
            WHERE id = :app
            FOR UPDATE
        """),
        {"app": app_id},
    ).scalar_one_or_none()

    if application_status is None:
        raise ApiProblem(404, "NOT_FOUND", "Заявка не найдена")
    if application_status not in ("CHECKING", "UNDER_REVIEW"):
        raise ApiProblem(
            409,
            "INVALID_STATE_TRANSITION",
            "Залог нельзя переоценивать после окончательного решения",
        )

    row = conn.execute(
        text("""
            SELECT id, status, has_encumbrance
            FROM alfa.application_collateral
            WHERE id = :id AND application_id = :app
            FOR UPDATE
        """),
        {"id": collateral_id, "app": app_id},
    ).mappings().first()

    if row is None:
        raise ApiProblem(404, "NOT_FOUND", "Залог не найден")

    if row["status"] not in ("DECLARED", "UNDER_REVIEW"):
        raise ApiProblem(
            409, "INVALID_STATE_TRANSITION",
            "Оценка залога уже завершена"
        )

    encumbrance = (
        data.has_encumbrance
        if data.has_encumbrance is not None
        else row["has_encumbrance"]
    )

    if data.status == "ACCEPTED":
        if encumbrance is None:
            raise ApiProblem(
                422, "ENCUMBRANCE_UNKNOWN",
                "Необходимо проверить обременения"
            )

        if encumbrance:
            raise ApiProblem(
                422, "ENCUMBERED_COLLATERAL",
                "Залог с обременением требует отдельной проверки"
            )

    final = data.status in ("ACCEPTED", "REJECTED")

    result = conn.execute(
        text("""
            UPDATE alfa.application_collateral
            SET status = :status,
                assessed_value = :value,
                has_encumbrance = :encumbrance,
                review_comment = :comment,
                reviewed_by = :reviewer,
                reviewed_at = CASE
                    WHEN :final THEN now()
                    ELSE NULL
                END
            WHERE id = :id AND application_id = :app
            RETURNING
                id, collateral_type, description,
                owner_name, ownership_type,
                declared_value, assessed_value,
                has_encumbrance, status, review_comment
        """),
        {
            "id": collateral_id,
            "app": app_id,
            "status": data.status,
            "value": data.assessed_value,
            "encumbrance": encumbrance,
            "comment": data.review_comment,
            "reviewer": actor.id if final else None,
            "final": final,
        },
    ).mappings().one()

    return dict(result)
