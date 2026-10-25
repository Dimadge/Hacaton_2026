from decimal import Decimal, ROUND_HALF_UP


# свободные деньги для выплаты кредитов
def calculate_cash_flow(revenue: Decimal, expenses: Decimal) -> Decimal:
    return revenue - expenses


# макс. ежемесячный плаьеж по новому кредиту. взяла коэф 40% от свободных денег - кредиты
def calculate_max_new_payment(
        cash_flow: Decimal,
        existing_debt: Decimal,
        payment_share: Decimal = Decimal("0.40")
) -> Decimal:
    if cash_flow <= Decimal("0.00"):
        return Decimal("0.00")

    limit = (payment_share * cash_flow) - existing_debt
    max_payment = max(Decimal("0.00"), limit)
    return max_payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# аннуитетный ежемесячный платеж
def calculate_annuity_payment(amount: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
    if term_months <= 0:
        return Decimal("0.00")

    if annual_rate == Decimal("0.00"):
        return (amount / Decimal(term_months)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Та же формула, что в триггере guard_offer: amount * r / (1 - (1+r)^-n), r = ставка/12.
    r = annual_rate / Decimal(12)
    payment = amount * r / (Decimal(1) - (Decimal(1) + r) ** (-term_months))
    return payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# обратный аннуитет макс. сумма займа под заданный платеж
def calculate_max_amount_by_payment(
        max_payment: Decimal,
        annual_rate: Decimal,
        term_months: int,
        step: Decimal = Decimal("10000")
) -> Decimal:

    if term_months <= 0 or max_payment <= Decimal("0.00") or annual_rate <= Decimal("0.00"):
        return Decimal("0.00")

    r = float(annual_rate) / 12.0
    n = float(term_months)
    pmt = float(max_payment)

    amount_raw = pmt * ((1.0 - ((1.0 + r) ** (-n))) / r)
    amount_dec = Decimal(str(amount_raw))

    floored_amount = (amount_dec // step) * step
    return max(Decimal("0.00"), floored_amount)