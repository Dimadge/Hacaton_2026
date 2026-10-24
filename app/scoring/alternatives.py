from decimal import Decimal
from typing import List
from app.scoring.contracts import OfferCandidate
from app.scoring.finance import calculate_annuity_payment, calculate_max_amount_by_payment


def generate_alternative_offers(
    requested_amount: Decimal,
    requested_term: int,
    rate: Decimal,
    max_payment: Decimal,
    max_product_term: int = 60,
    min_product_amount: Decimal = Decimal("500000.00")
) -> List[OfferCandidate]:

    candidates: List[OfferCandidate] = []

    # Вариант A. Сохранить сумму, увеличить срок
    # перебираем сроки с шагом 6 месяцев до максимума продукта
    for term in range(requested_term + 6, max_product_term + 1, 6):
        payment = calculate_annuity_payment(requested_amount, rate, term)
        if payment <= max_payment:
            candidates.append(
                OfferCandidate(
                    amount=requested_amount,
                    term_months=term,
                    rate=rate,
                    monthly_payment=payment
                )
            )
            break

    # Вариант B. Сохранить срок, уменьшить сумму
    adjusted_amount = calculate_max_amount_by_payment(max_payment, rate, requested_term)
    if adjusted_amount >= min_product_amount and adjusted_amount != requested_amount:
        payment = calculate_annuity_payment(adjusted_amount, rate, requested_term)
        candidates.append(
            OfferCandidate(
                amount=adjusted_amount,
                term_months=requested_term,
                rate=rate,
                monthly_payment=payment
            )
        )

    return candidates