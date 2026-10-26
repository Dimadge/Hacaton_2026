"""Преобразование сохранённой заявки и ФНС/БКИ в ScoringInput.
Расчёт скоринга и атомарное сохранение результатов в PostgreSQL.
"""
from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Connection, text

from ..core.errors import ApiProblem
from ..scoring.contracts import ScoringInput, ScoringOutput
from ..scoring import score_application
from ..scoring.bank_history import calculate_bank_score
from ..scoring.finance import calculate_cash_flow, calculate_annuity_payment


def build_scoring_input(conn: Connection, run_id: UUID) -> ScoringInput:
    row = conn.execute(text('''SELECT input_snapshot,product_snapshot
        FROM alfa.evaluation_runs WHERE id=:run'''), {'run': run_id}).mappings().first()
    if not row:
        raise ApiProblem(404, 'NOT_FOUND', 'Цикл проверки не найден')
    checks = conn.execute(text('''SELECT source,result FROM alfa.verifications
        WHERE run_id=:run'''), {'run': run_id}).mappings().all()
    values = {r['source']: r['result'] for r in checks}
    if set(values) != {'FNS', 'BKI'}:
        raise ApiProblem(409, 'VERIFICATIONS_INCOMPLETE',
                         'Нельзя запускать скоринг до завершения mock-проверок')
    snapshot = row['input_snapshot']
    product = row['product_snapshot']
    return ScoringInput(
        monthly_revenue=snapshot['monthly_revenue'],
        operating_expenses=snapshot['operating_expenses'],
        existing_debt_payments=snapshot['existing_debt_payments'],
        business_age_months=snapshot['business_age_months'],
        requested_amount=snapshot['requested_amount'],
        term_months=snapshot['term_months'],
        demo_rate=product['demo_rate'],
        min_amount=product.get('min_amount'),
        max_amount=product.get('max_amount'),
        min_term=product.get('min_term'),
        max_term=product.get('max_term'),
        credit_history_flag=values['BKI'],
        company_registry_flag=values['FNS'],
        bank_history=snapshot.get('bank_history'),
    )


def execute_and_save_scoring(conn: Connection, app_id: UUID) -> dict:
    app = conn.execute(
        text("SELECT id, status, version FROM alfa.loan_applications WHERE id=:app FOR UPDATE"),
        {"app": app_id},
    ).mappings().first()
    if not app:
        raise ApiProblem(404, "NOT_FOUND", "Заявка не найдена")
    run = conn.execute(
        text("""SELECT id, input_snapshot, product_snapshot, rule_version
                FROM alfa.evaluation_runs WHERE application_id=:app
                ORDER BY submission_version DESC LIMIT 1"""),
        {"app": app_id},
    ).mappings().first()
    if not run:
        raise ApiProblem(409, "NO_EVALUATION", "Цикл проверки не найден")

    run_id = run["id"]
    already = conn.execute(
        text("SELECT id, score, risk, factors FROM alfa.scoring_results WHERE run_id=:run"),
        {"run": run_id},
    ).mappings().first()
    if already:
        factors = already["factors"] or {}
        return {
            "application_id": str(app_id),
            "scoring_id": str(already["id"]),
            "score": already["score"],
            "risk": already["risk"],
            "decision_hint": factors.get("decision_hint"),
            "offers_count": 0,
            "status": app["status"],
        }
    inp = build_scoring_input(conn, run_id)
    out: ScoringOutput = score_application(inp)

    cash_flow = calculate_cash_flow(inp.monthly_revenue, inp.operating_expenses)
    req_payment = calculate_annuity_payment(inp.requested_amount, inp.demo_rate, inp.term_months)
    score_raw = Decimal(str(out.score)).quantize(Decimal("0.00001"))
    bank_factor = calculate_bank_score(inp.bank_history, inp.monthly_revenue)
    factors = {
        "monthly_revenue": str(inp.monthly_revenue),
        "operating_expenses": str(inp.operating_expenses),
        "existing_debt_payments": str(inp.existing_debt_payments),
        "business_age_months": inp.business_age_months,
        "cash_flow": str(cash_flow),
        "requested_payment": str(req_payment),
        "max_new_payment": str(out.max_new_monthly_payment),
        "decision_hint": out.decision_hint,
        "bank_history": inp.bank_history.model_dump(mode="json") if inp.bank_history else None,
        "bank_score": bank_factor.score,
        "bank_ratio": str(bank_factor.ratio) if bank_factor.ratio is not None else None,
        "bank_unstable": bank_factor.unstable,
    }
    scoring_id = conn.execute(
        text("""INSERT INTO alfa.scoring_results
                (application_id, run_id, score, score_raw, risk, max_new_payment,
                 cash_flow, requested_payment, factors)
                VALUES
                (:app, :run, :score, :score_raw, CAST(:risk AS alfa.risk_kind),
                 :max_new_payment, :cash_flow, :requested_payment, CAST(:factors AS jsonb))
                RETURNING id"""),
        {
            "app": app_id,
            "run": run_id,
            "score": out.score,
            "score_raw": score_raw,
            "risk": out.risk_level,
            "max_new_payment": out.max_new_monthly_payment,
            "cash_flow": cash_flow,
            "requested_payment": req_payment,
            "factors": json.dumps(factors),
        },
    ).scalar_one()
    for code in out.reason_codes:
        valid = conn.execute(
            text("SELECT 1 FROM alfa.reason_codes WHERE code=:code"),
            {"code": code},
        ).scalar_one_or_none()
        if valid:
            conn.execute(
                text("""INSERT INTO alfa.scoring_result_reasons (scoring_result_id, reason_code)
                        VALUES (:sid, :code) ON CONFLICT DO NOTHING"""),
                {"sid": scoring_id, "code": code},
            )
    return {
        "application_id": str(app_id),
        "scoring_id": str(scoring_id),
        "score": out.score,
        "risk": out.risk_level,
        "decision_hint": out.decision_hint,
        "offers_count": len(out.candidates),
        "status": app["status"],
    }
