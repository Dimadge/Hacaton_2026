from decimal import Decimal
from app.scoring import score_application
from app.scoring.contracts import ScoringInput


def test_sample_application_scoring():
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

    assert result.decision_hint == "COUNTER_OFFER"
    assert result.risk_level == "LOW"
    assert len(result.candidates) >= 1
    assert "PAYMENT_OVER_LIMIT" in result.reason_codes

    print("\n РЕЗУЛЬТАТ СКОРИНГА ")
    print(f"Балл: {result.score}/100")
    print(f"Уровень риска: {result.risk_level}")
    print(f"Лимит нового платежа: {result.max_new_monthly_payment} руб.")
    print(f"Вердикт: {result.decision_hint}")
    print(f"Коды причин: {result.reason_codes}")
    print(f"Офферы ({len(result.candidates)} шт.):")
    for i, c in enumerate(result.candidates, 1):
        print(f"  {i}) Сумма: {c.amount:,.0f} руб. | Срок: {c.term_months} мес. | Платеж: {c.monthly_payment:,.2f} руб.")