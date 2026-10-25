"""Клиентский и банковский REST-контракт BE-07."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class BankQueueItem(BaseModel):
    id: UUID
    company_id: UUID
    company_name: str
    status: str
    product_code: str
    requested_amount: Decimal
    term_months: int
    version: int
    created_at: datetime


class BankApplicationOut(BankQueueItem):
    document_confirmed: bool
    evaluation_run_id: UUID | None
    verification_results: dict[str, str]
    scoring_ready: bool
    client_clarification: str | None = None


class EvaluateOut(BaseModel):
    application_id: UUID
    status: str
    version: int
    decision_type: str | None
    reason_codes: list[str]
    next_step: str


class ManualOffer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount: Decimal = Field(gt=0)
    term_months: int = Field(gt=0)

    @field_validator('amount', mode='before')
    @classmethod
    def forbid_float(cls, value):
        if isinstance(value, float):
            raise ValueError('Сумма кредита должна быть строкой, не JSON float')
        return value


class BankDecisionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(gt=0)
    action: Literal['REQUEST_INFO', 'REJECT', 'APPROVE']
    reason_codes: list[str] = Field(default_factory=list, max_length=10)
    comment: str | None = Field(default=None, max_length=2000)
    offers: list[ManualOffer] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def check_action(self):
        if self.action == 'APPROVE':
            if not self.offers:
                raise ValueError('APPROVE требует хотя бы одно предложение')
        elif self.offers:
            raise ValueError('Предложения допустимы только для APPROVE')
        if self.action in ('REJECT', 'REQUEST_INFO') and not self.reason_codes:
            raise ValueError('Укажите хотя бы одну причину')
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError('Коды причин не должны повторяться')
        return self


class OfferOut(BaseModel):
    id: UUID
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal
    rank: int
    accepted: bool


class OffersOut(BaseModel):
    application_id: UUID
    application_status: str
    decision_id: UUID | None
    decision_type: str | None
    reason_codes: list[str]
    offers: list[OfferOut]
