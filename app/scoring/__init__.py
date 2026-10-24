from decimal import Decimal
from typing import List

from app.scoring.contracts import ScoringInput, ScoringOutput, OfferCandidate
from app.scoring.finance import (
    calculate_cash_flow,
    calculate_max_new_payment,
    calculate_annuity_payment,
)
from app.scoring.rules import evaluate_score_and_risk
from app.scoring.alternatives import generate_alternative_offers

RULE_VERSION = "rules-v1"


def score_application(data: ScoringInput) -> ScoringOutput:
    reasons: List[str] = []

    # расчет финансовых лимитов
    cash_flow = calculate_cash_flow(data.monthly_revenue, data.operating_expenses)
    max_payment = calculate_max_new_payment(cash_flow, data.existing_debt_payments)
    requested_payment = calculate_annuity_payment(
        data.requested_amount, data.demo_rate, data.term_months
    )

    # оценка рейтинга заемщика и категории риска
    score, risk_level, score_reasons = evaluate_score_and_risk(
        revenue=data.monthly_revenue,
        expenses=data.operating_expenses,
        existing_debt=data.existing_debt_payments,
        business_age_months=data.business_age_months,
        credit_history_flag=data.credit_history_flag,
        company_registry_flag=data.company_registry_flag,
    )
    reasons.extend(score_reasons)

    candidates: List[OfferCandidate] = []

    # формирование рекомендаций по решению
    if data.company_registry_flag == "inactive":
        decision_hint = "REJECT"
    elif data.credit_history_flag == "critical":
        decision_hint = "REJECT"
    elif risk_level == "HIGH":
        decision_hint = "REJECT"
    elif (
        data.company_registry_flag in ("mismatch", "unknown")
        or data.credit_history_flag in ("minor_delay", "unknown")
        or risk_level == "MEDIUM"
    ):
        decision_hint = "MANUAL_REVIEW"
    else:
        if requested_payment <= max_payment:
            decision_hint = "APPROVE"
            candidates.append(
                OfferCandidate(
                    amount=data.requested_amount,
                    term_months=data.term_months,
                    rate=data.demo_rate,
                    monthly_payment=requested_payment,
                )
            )
        else:
            decision_hint = "COUNTER_OFFER"
            if "PAYMENT_OVER_LIMIT" not in reasons:
                reasons.append("PAYMENT_OVER_LIMIT")

            candidates = generate_alternative_offers(
                requested_amount=data.requested_amount,
                requested_term=data.term_months,
                rate=data.demo_rate,
                max_payment=max_payment,
            )
            if not candidates:
                decision_hint = "REJECT"

    unique_reasons = list(dict.fromkeys(reasons))

    return ScoringOutput(
        score=score,
        risk_level=risk_level,
        max_new_monthly_payment=max_payment,
        decision_hint=decision_hint,
        candidates=candidates,
        reason_codes=unique_reasons,
        rule_version=RULE_VERSION,
    )