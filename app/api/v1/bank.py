"""Кабинет сотрудника банка (только JWT роль BANK_EMPLOYEE)."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import Connection
from ...core.security import Actor, require_bank_employee
from ...database import get_connection
from ...schemas.decision import (BankQueueItem, BankApplicationOut,
                                 BankDecisionIn, EvaluateOut)
from ...services import decisions
from ...services.scoring_adapter import execute_and_save_scoring
from ...schemas.collateral import CollateralOut
from ...services import collateral as collateral_service
from decimal import Decimal
from ...scoring.explain import calculate_score_breakdown, generate_bank_underwriter_summary
from sqlalchemy import Connection, text
from ...core.errors import ApiProblem

router = APIRouter(prefix='/bank', tags=['Банк'])


@router.get('/applications', response_model=list[BankQueueItem],
            summary='Очередь CHECKING, UNDER_REVIEW и NEED_INFO')
def queue(_actor: Actor = Depends(require_bank_employee),
          conn: Connection = Depends(get_connection)):
    return decisions.bank_queue(conn)


@router.get('/applications/{application_id}', response_model=BankApplicationOut,
            summary='Карточка заявки для банковского сотрудника')
def application(application_id: UUID,
                _actor: Actor = Depends(require_bank_employee),
                conn: Connection = Depends(get_connection)):
    return decisions.bank_application(conn, application_id)


@router.get('/applications/{application_id}/collateral', response_model=list[CollateralOut],
            summary='Залог по заявке для сотрудника')
def application_collateral(application_id: UUID,
                           _actor: Actor = Depends(require_bank_employee),
                           conn: Connection = Depends(get_connection)):
    return collateral_service.list_for_bank(conn, application_id)


@router.post('/applications/{application_id}/evaluate', response_model=EvaluateOut,
             summary='Применить правила к ФНС/БКИ; не подменяет скоринг DS')
def evaluate(application_id: UUID,
             actor: Actor = Depends(require_bank_employee),
             conn: Connection = Depends(get_connection)):
    return decisions.bank_evaluate(conn, actor, application_id)


@router.post('/applications/{application_id}/decision', response_model=EvaluateOut,
             summary='Решение сотрудника по UNDER_REVIEW (с проверкой версии)')
def decision(application_id: UUID, data: BankDecisionIn,
             actor: Actor = Depends(require_bank_employee),
             conn: Connection = Depends(get_connection)):
    return decisions.manual_decision(conn, actor, application_id, data)

@router.post('/applications/{application_id}/score')
def run_scoring(application_id: UUID, actor: Actor = Depends(require_bank_employee),
                conn: Connection = Depends(get_connection)):
    return execute_and_save_scoring(conn, application_id)

@router.get('/applications/{application_id}/scoring-analysis',
            summary='Пофакторная расшифровка скоринга и заключение для андеррайтера')
async def get_scoring_analysis(application_id: UUID,
                               conn: Connection = Depends(get_connection)):
    run = conn.execute(
        text("""SELECT r.id, r.input_snapshot, s.id as scoring_id, s.score, s.risk
                FROM alfa.evaluation_runs r
                LEFT JOIN alfa.scoring_results s ON s.run_id=r.id
                WHERE r.application_id=:app
                ORDER BY r.submission_version DESC LIMIT 1"""),
        {"app": application_id},
    ).mappings().first()

    if not run or not run["scoring_id"]:
        raise ApiProblem(409, "SCORING_NOT_FOUND", "Скоринг по заявке еще не выполнен")

    checks = conn.execute(
        text("SELECT source, result FROM alfa.verifications WHERE run_id=:run"),
        {"run": run["id"]},
    ).mappings().all()
    check_values = {c["source"]: c["result"] for c in checks}

    decision = conn.execute(
        text("""SELECT id, decision_type FROM alfa.credit_decisions
                WHERE run_id=:run ORDER BY sequence_no DESC LIMIT 1"""),
        {"run": run["id"]},
    ).mappings().first()

    reasons = []
    if decision:
        reasons = conn.execute(
            text("SELECT reason_code FROM alfa.decision_reasons WHERE decision_id=:dec"),
            {"dec": decision["id"]},
        ).scalars().all()

    snapshot = run["input_snapshot"]

    breakdown = calculate_score_breakdown(
        revenue=Decimal(str(snapshot["monthly_revenue"])),
        expenses=Decimal(str(snapshot["operating_expenses"])),
        existing_debt=Decimal(str(snapshot["existing_debt_payments"])),
        business_age_months=int(snapshot["business_age_months"]),
        credit_history_flag=check_values.get("BKI", "good"),
        company_registry_flag=check_values.get("FNS", "active"),
    )

    decision_type = decision["decision_type"] if decision else "MANUAL_REVIEW"

    summary = await generate_bank_underwriter_summary(
        score=run["score"],
        risk_level=run["risk"],
        decision_type=decision_type,
        reasons=list(reasons),
        breakdown=breakdown,
    )

    return {
        "application_id": str(application_id),
        "score": run["score"],
        "risk_level": run["risk"],
        "decision_type": decision_type,
        "reason_codes": list(reasons),
        "factors_breakdown": breakdown,
        "underwriter_summary": summary,
    }