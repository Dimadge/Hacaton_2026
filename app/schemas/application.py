"""Внешний контракт для фронтенда: Decimal передаётся строками, не JSON float."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
Amount = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]


class NoFloatMoney(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('monthly_revenue', 'operating_expenses', 'existing_debt_payments',
                     'cash_reserve', 'requested_amount', mode='before', check_fields=False)
    @classmethod
    def prohibit_json_float(cls, value):
        if isinstance(value, float) or isinstance(value, bool):
            raise ValueError('Денежные значения передавайте строкой, например "1500000.00"')
        return value


class FinancialsIn(NoFloatMoney):
    monthly_revenue: Money
    operating_expenses: Money
    existing_debt_payments: Money
    business_age_months: int = Field(ge=0, le=1200)
    cash_reserve: Money | None = None
    document_confirmed: bool = False


class FinancialsPatch(NoFloatMoney):
    monthly_revenue: Money | None = None
    operating_expenses: Money | None = None
    existing_debt_payments: Money | None = None
    business_age_months: int | None = Field(default=None, ge=0, le=1200)
    cash_reserve: Money | None = None
    document_confirmed: bool | None = None


class ApplicationCreate(NoFloatMoney):
    product_code: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=500)
    requested_amount: Amount
    term_months: int = Field(ge=1, le=600)
    financials: FinancialsIn

    @field_validator('purpose')
    @classmethod
    def purpose_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Укажите цель кредита')
        return value.strip()


class ApplicationPatch(NoFloatMoney):
    version: int = Field(ge=1)
    purpose: str | None = Field(default=None, min_length=1, max_length=500)
    requested_amount: Amount | None = None
    term_months: int | None = Field(default=None, ge=1, le=600)
    financials: FinancialsPatch | None = None

    @field_validator('purpose')
    @classmethod
    def purpose_not_blank(cls, value: str | None):
        if value is not None and not value.strip():
            raise ValueError('Укажите цель кредита')
        return value.strip() if value is not None else None

    @model_validator(mode='after')
    def check_changes(self):
        if all(getattr(self, item) is None for item in ('purpose', 'requested_amount', 'term_months', 'financials')):
            raise ValueError('Укажите хотя бы одно изменяемое поле')
        if self.financials is not None and not self.financials.model_fields_set:
            raise ValueError('financials не может быть пустым объектом')
        return self


class ProductOut(BaseModel):
    id: UUID
    code: str
    name: str
    min_amount: Decimal
    max_amount: Decimal
    min_term: int
    max_term: int
    demo_rate: Decimal


class CompanyOut(BaseModel):
    id: UUID
    name: str
    inn: str
    industry: str
    registered_at: str


class ApplicationOut(BaseModel):
    id: UUID
    company_id: UUID
    product_code: str
    purpose: str
    requested_amount: Decimal
    term_months: int
    status: str
    version: int
    created_at: datetime
    financials: FinancialsIn


class ApplicationSummary(BaseModel):
    id: UUID
    status: str
    product_code: str
    requested_amount: Decimal
    term_months: int
    version: int
    created_at: datetime


class EventOut(BaseModel):
    id: int
    action: str
    from_status: str | None
    to_status: str
    application_version: int
    at: datetime


class ApplicationSubmit(BaseModel):
    """Оптимистическая блокировка: версия из последнего GET заявки."""
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    clarification: str | None = Field(default=None, min_length=10, max_length=2000,
        description='Пояснение клиента по запросу сотрудника банка (для повторной подачи)')

    @field_validator('clarification')
    @classmethod
    def normalized_clarification(cls, value: str | None):
        if value is None:
            return None
        if not value.strip() or len(value.strip()) < 10:
            raise ValueError('Пояснение должно содержать не менее 10 символов')
        return value.strip()


class SubmissionOut(BaseModel):
    id: UUID
    status: str
    version: int
    evaluation_run_id: UUID
