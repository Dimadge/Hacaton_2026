import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
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


def _sign_code_digest(application_id: UUID, salt: str, code: str) -> str:
    # HMAC with server secret means leaked DB hash cannot be brute-forced alone.
    key = os.environ["JWT_SECRET"].encode("utf-8")
    message = f"contract-sign:{application_id}:{salt}:{code}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def request_signing_code(
    conn: Connection, actor: Actor, app_id: UUID, version: int,
) -> dict:
    if os.getenv("DEMO_SIGNING_CODE_VISIBLE", "false").lower() != "true":
        raise ApiProblem(
            503, "DEMO_CODE_DISABLED", "Демонстрационная выдача кода отключена"
        )

    _lock(conn, actor, app_id, version, "ACCEPTED")
    now = datetime.now(timezone.utc)
    old = conn.execute(text("""
        SELECT requested_at FROM alfa.signing_codes
        WHERE application_id = :app FOR UPDATE
    """), {"app": app_id}).mappings().first()
    if old and (now - old["requested_at"]).total_seconds() < 30:
        raise ApiProblem(429, "SIGN_CODE_RATE_LIMIT", "Повторите запрос через 30 секунд")

    code = f"{secrets.randbelow(1000000):06d}"
    salt = secrets.token_hex(16)
    digest = _sign_code_digest(app_id, salt, code)
    conn.execute(text("""
        INSERT INTO alfa.signing_codes (
            application_id, code_hash, salt,
            expires_at, requested_at, attempts, used_at
        ) VALUES (:app, :digest, :salt, :expires, :requested, 0, NULL)
        ON CONFLICT (application_id) DO UPDATE SET
            code_hash = EXCLUDED.code_hash,
            salt = EXCLUDED.salt,
            expires_at = EXCLUDED.expires_at,
            requested_at = EXCLUDED.requested_at,
            attempts = 0,
            used_at = NULL
    """), {
        "app": app_id, "digest": digest, "salt": salt,
        "expires": now + timedelta(minutes=5), "requested": now,
    })
    # Synthetic on-screen code ONLY in explicitly enabled local demo mode.
    return {"expires_in_seconds": 300, "demo_code": code}


def sign_application(
    conn: Connection, actor: Actor, app_id: UUID, version: int, code: str,
) -> dict:
    _lock(conn, actor, app_id, version, "ACCEPTED")
    otp = conn.execute(text("""
        SELECT code_hash, salt, expires_at, attempts, used_at
        FROM alfa.signing_codes
        WHERE application_id = :app FOR UPDATE
    """), {"app": app_id}).mappings().first()

    if otp is None:
        raise ApiProblem(409, "SIGN_CODE_REQUIRED", "Сначала запросите код")
    if otp["used_at"] is not None:
        raise ApiProblem(409, "SIGN_CODE_USED", "Код уже использован")
    if datetime.now(timezone.utc) >= otp["expires_at"]:
        raise ApiProblem(409, "SIGN_CODE_EXPIRED", "Срок действия кода истёк")
    if otp["attempts"] >= 5:
        raise ApiProblem(429, "SIGN_CODE_BLOCKED", "Попытки исчерпаны")

    entered = _sign_code_digest(app_id, otp["salt"], code)
    if not hmac.compare_digest(entered, otp["code_hash"]):
        conn.execute(text("""
            UPDATE alfa.signing_codes
            SET attempts = attempts + 1
            WHERE application_id = :app
        """), {"app": app_id})
        # Return sentinel so get_connection commits failed-attempt counter.
        # Route below turns it into a 422 HTTP response.
        return {"_bad_code": True}

    conn.execute(text("""
        UPDATE alfa.signing_codes
        SET used_at = now()
        WHERE application_id = :app
    """), {"app": app_id})
    return _update(conn, actor, app_id, version, "ACCEPTED", "SIGNED")


def simulate_disbursement(conn: Connection, actor: Actor, app_id: UUID, version: int) -> dict:
    _lock(conn, actor, app_id, version, 'SIGNED')
    return _update(conn, actor, app_id, version, 'SIGNED', 'DISBURSED')


def cancel_offer(conn: Connection, actor: Actor, app_id: UUID, version: int) -> dict:
    _lock(conn, actor, app_id, version, 'OFFERED')
    return _update(conn, actor, app_id, version, 'OFFERED', 'CANCELLED')
