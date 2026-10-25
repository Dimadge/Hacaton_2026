"""Договорённый интерфейс для DS; scoring здесь намеренно НЕ реализован.

Все денежные значения Decimal, никогда float. Реальный scorer подключим в BE-07.
"""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictMoney(BaseModel):
    @field_validator('monthly_revenue', 'operating_expenses',
                     'existing_debt_payments', 'requested_amount', 'demo_rate',
                     'amount', 'rate', 'monthly_payment',
                     'max_new_monthly_payment', check_fields=False, mode='before')
    @classmethod
    def no_float_for_decimal(cls, value):
        if isinstance(value, float):
            raise ValueError('Денежные поля и ставки должны передаваться Decimal или строкой')
        return value


class ScoringInput(StrictMoney):
    model_config = ConfigDict(extra='forbid')
    monthly_revenue: Decimal = Field(ge=0)
    operating_expenses: Decimal = Field(ge=0)
    existing_debt_payments: Decimal = Field(ge=0)
    business_age_months: int = Field(ge=0)
    requested_amount: Decimal = Field(gt=0)
    term_months: int = Field(gt=0)
    demo_rate: Decimal = Field(ge=0, le=1)
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    min_term: int | None = None
    max_term: int | None = None
    credit_history_flag: Literal['good', 'minor_delay', 'critical', 'unknown']
    company_registry_flag: Literal['active', 'inactive', 'mismatch', 'unknown']


class OfferCandidate(StrictMoney):
    amount: Decimal = Field(gt=0)
    term_months: int = Field(gt=0)
    rate: Decimal = Field(ge=0, le=1)
    monthly_payment: Decimal = Field(ge=0)


class ScoringOutput(StrictMoney):
    model_config = ConfigDict(extra='forbid')
    score: int = Field(ge=0, le=100)
    risk_level: Literal['LOW', 'MEDIUM', 'HIGH']
    max_new_monthly_payment: Decimal = Field(ge=0)
    decision_hint: Literal['APPROVE','COUNTER_OFFER','MANUAL_REVIEW','REQUEST_INFO','REJECT']
    candidates: list[OfferCandidate]
    reason_codes: list[str]
    rule_version: str
