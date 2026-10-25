from uuid import UUID
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy import Connection, text
from ...core.errors import ApiProblem
from ...core.security import Actor, require_client
from ...database import get_connection
from ...schemas.application import (ApplicationCreate, ApplicationPatch,
    ApplicationOut, ApplicationSummary, EventOut, ApplicationSubmit, SubmissionOut)
from ...services import applications as service
from ...services import workflow, checks
from ...schemas.checks import ChecksOut
from ...schemas.decision import OffersOut
from ...services import decisions, fulfillment
from ...schemas.fulfillment import AcceptOfferIn, VersionedAction, FulfillmentOut
from ...scoring.explain import generate_explanation

router = APIRouter(prefix='/applications', tags=['Заявки'])


@router.get('', response_model=list[ApplicationSummary])
def list_applications(actor: Actor = Depends(require_client), conn: Connection = Depends(get_connection)):
    return service.list_mine(conn, actor)


@router.post('', status_code=status.HTTP_201_CREATED, response_model=ApplicationOut)
def create_application(data: ApplicationCreate, actor: Actor = Depends(require_client),
                       conn: Connection = Depends(get_connection)):
    return service.create_one(conn, actor, data)


@router.get('/{application_id}', response_model=ApplicationOut)
def get_application(application_id: UUID, actor: Actor = Depends(require_client),
                    conn: Connection = Depends(get_connection)):
    return service.get_one(conn, actor, application_id)


@router.patch('/{application_id}', response_model=ApplicationOut)
def patch_application(application_id: UUID, data: ApplicationPatch,
                      actor: Actor = Depends(require_client),
                      conn: Connection = Depends(get_connection)):
    return service.update_one(conn, actor, application_id, data)


@router.get('/{application_id}/events', response_model=list[EventOut])
def get_events(application_id: UUID, actor: Actor = Depends(require_client),
               conn: Connection = Depends(get_connection)):
    return service.events_for(conn, actor, application_id)


@router.post('/{application_id}/submit', response_model=SubmissionOut,
             summary='Отправить DRAFT или повторно направить NEED_INFO на проверку')
def submit_application(application_id: UUID, data: ApplicationSubmit,
                       idempotency_key: str | None = Header(default=None, alias='Idempotency-Key',
                                                            min_length=1, max_length=200),
                       actor: Actor = Depends(require_client),
                       conn: Connection = Depends(get_connection)):
    submitted = workflow.submit_one(conn, actor, application_id, data.version, idempotency_key,
                                   clarification=data.clarification)
    # BE-06: в той же транзакции сохраняем детерминированные mock ФНС/БКИ.
    # Если сохранение не удалось, submit полностью откатится.
    checks.ensure_checks(conn, actor, application_id)
    return submitted


@router.get('/{application_id}/checks', response_model=ChecksOut,
            summary='Посмотреть сохранённые результаты mock ФНС и БКИ')
def get_verification_checks(application_id: UUID,
                            actor: Actor = Depends(require_client),
                            conn: Connection = Depends(get_connection)):
    return checks.get_checks(conn, actor, application_id)


@router.post('/{application_id}/checks/run', response_model=ChecksOut,
             summary='Запустить mock-проверки для ранее отправленной заявки')
def run_verification_checks(application_id: UUID,
                            actor: Actor = Depends(require_client),
                            conn: Connection = Depends(get_connection)):
    return checks.ensure_checks(conn, actor, application_id)


@router.get('/{application_id}/offers', response_model=OffersOut,
            summary='Решение, причины и предложения для клиента')
def get_application_offers(application_id: UUID,
                           actor: Actor = Depends(require_client),
                           conn: Connection = Depends(get_connection)):
    return decisions.get_offers(conn, actor, application_id)


@router.post('/{application_id}/accept', response_model=FulfillmentOut,
             summary='Принять действующий кредитный оффер (только OFFERED)')
def accept(application_id: UUID, data: AcceptOfferIn,
           actor: Actor = Depends(require_client),
           conn: Connection = Depends(get_connection)):
    return fulfillment.accept_offer(conn, actor, application_id, data.version, data.offer_id)


@router.post('/{application_id}/sign', response_model=FulfillmentOut,
             summary='Симулировать подписание договора (только ACCEPTED)')
def sign(application_id: UUID, data: VersionedAction,
         actor: Actor = Depends(require_client),
         conn: Connection = Depends(get_connection)):
    return fulfillment.sign_application(conn, actor, application_id, data.version)


@router.post('/{application_id}/disburse', response_model=FulfillmentOut,
             summary='Демонстрационная выдача без реального движения средств (только SIGNED)')
def disburse(application_id: UUID, data: VersionedAction,
             actor: Actor = Depends(require_client),
             conn: Connection = Depends(get_connection)):
    return fulfillment.simulate_disbursement(conn, actor, application_id, data.version)


@router.post('/{application_id}/cancel', response_model=FulfillmentOut,
             summary='Отказаться от предложения (только OFFERED)')
def cancel(application_id: UUID, data: VersionedAction,
           actor: Actor = Depends(require_client),
           conn: Connection = Depends(get_connection)):
    return fulfillment.cancel_offer(conn, actor, application_id, data.version)

@router.get('/{application_id}/explanation')
async def get_application_explanation(
    application_id: UUID,
    actor: Actor = Depends(require_client),
    conn: Connection = Depends(get_connection),
):
    app = conn.execute(
        text("SELECT id, amount, term, status FROM alfa.loan_applications WHERE id=:app AND company_id=:cid"),
        {"app": application_id, "cid": actor.company_id},
    ).mappings().first()
    if not app:
        raise ApiProblem(404, "NOT_FOUND", "Заявка не найдена")

    run = conn.execute(
        text("""SELECT r.id, s.max_new_payment
                FROM alfa.evaluation_runs r
                LEFT JOIN alfa.scoring_results s ON s.run_id=r.id
                WHERE r.application_id=:app
                ORDER BY r.submission_version DESC LIMIT 1"""),
        {"app": application_id},
    ).mappings().first()
    if not run or not run["max_new_payment"]:
        raise ApiProblem(409, "SCORING_NOT_FOUND", "Скоринг по заявке еще не выполнен")

    decision = conn.execute(
        text("""SELECT id, decision_type FROM alfa.credit_decisions
                WHERE run_id=:run ORDER BY sequence_no DESC LIMIT 1"""),
        {"run": run["id"]},
    ).mappings().first()
    if not decision:
        raise ApiProblem(409, "DECISION_NOT_FOUND", "Решение по заявке еще не сформировано")

    reasons = conn.execute(
        text("SELECT reason_code FROM alfa.decision_reasons WHERE decision_id=:dec"),
        {"dec": decision["id"]},
    ).scalars().all()

    offers_raw = conn.execute(
        text("""SELECT amount, term, monthly_payment FROM alfa.credit_offers
                WHERE decision_id=:dec ORDER BY rank ASC"""),
        {"dec": decision["id"]},
    ).mappings().all()

    offers = [
        {"amount": o["amount"], "term_months": o["term"], "monthly_payment": o["monthly_payment"]}
        for o in offers_raw
    ]

    explanation = await generate_explanation(
        decision_type=decision["decision_type"],
        requested_amount=app["amount"],
        requested_term=app["term"],
        max_payment=run["max_new_payment"],
        offers=offers,
        reason_codes=list(reasons),
    )

    return {
        "application_id": str(application_id),
        "decision_type": decision["decision_type"],
        "explanation": explanation,
        "offers_available": len(offers),
    }