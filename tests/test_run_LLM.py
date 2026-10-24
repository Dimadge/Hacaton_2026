from decimal import Decimal
from app.scoring import score_application
from app.scoring.contracts import ScoringInput
from app.scoring.explain import explain_scoring_decision

sample_input = ScoringInput(
    monthly_revenue=Decimal("1500000.00"),
    operating_expenses=Decimal("900000.00"),
    existing_debt_payments=Decimal("150000.00"),
    business_age_months=36,
    requested_amount=Decimal("3000000.00"),
    term_months=36,
    demo_rate=Decimal("0.18"),
    credit_history_flag="good",
    company_registry_flag="active",
)

result = score_application(sample_input)
text = explain_scoring_decision(
    result,
    sample_input.requested_amount,
    sample_input.term_months
)

print("\n ОТВЕТ СИСТЕМЫ ")
print(text)