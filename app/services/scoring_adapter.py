"""Преобразование сохранённой версии заявки + ФНС/БКИ в ScoringInput,
расчет скоринга DS и атомарное сохранение результатов в PostgreSQL.
"""
from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID
from sqlalchemy import Connection, text

from ..core.errors import ApiProblem
from ..scoring.contracts import ScoringInput, ScoringOutput
from ..scoring import score_application
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
        credit_history_flag=values['BKI'],
        company_registry_flag=values['FNS'],
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
        text("SELECT id, score, risk FROM alfa.scoring_results WHERE run_id=:run"),
        {"run": run_id},
    ).mappings().first()
    if already:
        return {
            "application_id": str(app_id),
            "scoring_id": str(already["id"]),
            "score": already["score"],
            "risk": already["risk"],
            "status": app["status"],
        }

    inp = build_scoring_input(conn, run_id)
    out: ScoringOutput = score_application(inp)

    cash_flow = calculate_cash_flow(inp.monthly_revenue, inp.operating_expenses)
    req_payment = calculate_annuity_payment(inp.requested_amount, inp.demo_rate, inp.term_months)
    score_raw = Decimal(str(out.score)).quantize(Decimal("0.00001"))

    factors = {
        "monthly_revenue": str(inp.monthly_revenue),
        "operating_expenses": str(inp.operating_expenses),
        "existing_debt_payments": str(inp.existing_debt_payments),
        "business_age_months": inp.business_age_months,
        "cash_flow": str(cash_flow),
        "requested_payment": str(req_payment),
        "max_new_payment": str(out.max_new_monthly_payment),
        "decision_hint": out.decision_hint,
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

    target_status = app["status"]
    if out.candidates and out.decision_hint in ("APPROVE", "COUNTER_OFFER"):
        next_seq = conn.execute(
            text("SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM alfa.credit_decisions WHERE run_id=:run"),
            {"run": run_id},
        ).scalar_one()

        decision_id = conn.execute(
            text("""INSERT INTO alfa.credit_decisions
                    (application_id, run_id, sequence_no, decision_type, created_by, comment)
                    VALUES (:app, :run, :seq, CAST(:kind AS alfa.decision_kind), NULL, :comment)
                    RETURNING id"""),
            {
                "app": app_id,
                "run": run_id,
                "seq": next_seq,
                "kind": out.decision_hint,
                "comment": "Автоматический подбор условий на основе оценки DS",
            },
        ).scalar_one()

        for code in out.reason_codes:
            conn.execute(
                text("""INSERT INTO alfa.decision_reasons (decision_id, reason_code)
                        VALUES (:dec_id, :code) ON CONFLICT DO NOTHING"""),
                {"dec_id": decision_id, "code": code},
            )

        for rank, cand in enumerate(out.candidates, start=1):
            conn.execute(
                text("""INSERT INTO alfa.credit_offers
                        (application_id, decision_id, amount, term, rate, monthly_payment, rank)
                        VALUES (:app, :dec, :amount, :term, :rate, :pmt, :rank)"""),
                {
                    "app": app_id,
                    "dec": decision_id,
                    "amount": cand.amount,
                    "term": cand.term_months,
                    "rate": cand.rate,
                    "pmt": cand.monthly_payment,
                    "rank": rank,
                },
            )

        conn.execute(text("SELECT set_config('app.actor_id', '', true)"))
        conn.execute(
            text("""UPDATE alfa.loan_applications
                    SET status='OFFERED'
                    WHERE id=:app AND version=:ver"""),
            {"app": app_id, "ver": app["version"]},
        )
        target_status = "OFFERED"

    return {
        "application_id": str(app_id),
        "scoring_id": str(scoring_id),
        "score": out.score,
        "risk": out.risk_level,
        "decision_hint": out.decision_hint,
        "offers_count": len(out.candidates),
        "status": target_status,
    }