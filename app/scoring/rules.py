from decimal import Decimal
from typing import Tuple, List, Literal


def evaluate_score_and_risk(
    revenue: Decimal,
    expenses: Decimal,
    existing_debt: Decimal,
    business_age_months: int,
    credit_history_flag: str,
    company_registry_flag: str
) -> Tuple[int, Literal["LOW", "MEDIUM", "HIGH"], List[str]]:

    reasons: List[str] = []

    # X1 - выручка и денежный поток (вес 30%)
    cash_flow = revenue - expenses
    if revenue <= Decimal("0.00") or cash_flow <= Decimal("0.00"):
        x1 = 0
        reasons.append("CASHFLOW_NONPOSITIVE")
    else:
        margin = cash_flow / revenue
        if margin >= Decimal("0.40"):
            x1 = 100
        elif margin >= Decimal("0.20"):
            x1 = 75
        else:
            x1 = 50

    # X2 - долговая нагрузка DTI (вес 25%)
    if cash_flow <= Decimal("0.00"):
        x2 = 0
    else:
        dti = existing_debt / cash_flow
        if existing_debt == Decimal("0.00"):
            x2 = 100
        elif dti <= Decimal("0.25"):
            x2 = 80
        elif dti <= Decimal("0.40"):
            x2 = 60
        elif dti <= Decimal("0.60"):
            x2 = 40
        else:
            x2 = 10

    # X3 - кредитная история из mock БКИ (вес 20%)
    if credit_history_flag == "good":
        x3 = 100
    elif credit_history_flag == "minor_delay":
        x3 = 60
        reasons.append("CREDIT_HISTORY_DELAY")
    elif credit_history_flag == "critical":
        x3 = 10
        reasons.append("CREDIT_HISTORY_CRITICAL")
    else:
        x3 = 50
        reasons.append("UNKNOWN_VERIFICATION")

    # X4 - статус организации из mock ФНС (вес 15%)
    if company_registry_flag == "active":
        x4 = 100
    elif company_registry_flag == "mismatch":
        x4 = 50
        reasons.append("REGISTRY_MISMATCH")
    elif company_registry_flag == "inactive":
        x4 = 0
        reasons.append("REGISTRY_INACTIVE")
    else:
        x4 = 50
        reasons.append("UNKNOWN_VERIFICATION")

    # X5 - срок существования бизнеса (вес 10%)
    # 60 месяцев (5 лет) и более = 100 баллов
    x5 = min(100, int((business_age_months / 60) * 100))

    # итоговый балл
    raw_score = 0.30 * x1 + 0.25 * x2 + 0.20 * x3 + 0.15 * x4 + 0.10 * x5
    score = int(round(raw_score))
    score = max(0, min(100, score))

    if score >= 75:
        risk_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    elif score >= 50:
        risk_level = "MEDIUM"
        reasons.append("RISK_MEDIUM")
    else:
        risk_level = "HIGH"
        reasons.append("RISK_HIGH")

    return score, risk_level, reasons