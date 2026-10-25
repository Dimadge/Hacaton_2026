"""Предмет залога. Деньги приходят строкой, не JSON-числом."""
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .application import Amount


class CollateralIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    collateral_type: Literal['LAND', 'REAL_ESTATE', 'VEHICLE']
    description: str = Field(min_length=1, max_length=4000)
    owner_name: str = Field(min_length=1, max_length=500)
    ownership_type: Literal['BORROWER', 'THIRD_PARTY']
    declared_value: Amount
    has_encumbrance: bool | None = None

    @field_validator('declared_value', mode='before')
    @classmethod
    def prohibit_json_float(cls, value):
        if isinstance(value, float) or isinstance(value, bool):
            raise ValueError('Денежные значения передавайте строкой, например "1500000.00"')
        return value

    @field_validator('description', 'owner_name')
    @classmethod
    def not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError('Заполните поле')
        return text


class CollateralOut(BaseModel):
    id: UUID
    collateral_type: str
    description: str
    owner_name: str
    ownership_type: str
    declared_value: Decimal
    assessed_value: Decimal | None
    has_encumbrance: bool | None
    status: str
    review_comment: str | None


class CollateralReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["UNDER_REVIEW", "ACCEPTED", "REJECTED"]
    assessed_value: Amount | None = None
    has_encumbrance: bool | None = None
    review_comment: str | None = Field(
        default=None, max_length=4000
    )

    @field_validator("assessed_value", mode="before")
    @classmethod
    def validate_money(cls, value):
        if isinstance(value, (bool, float)):
            raise ValueError("Стоимость передавайте строкой")
        return value

    @model_validator(mode="after")
    def validate_review(self):
        if self.status == "ACCEPTED" and self.assessed_value is None:
            raise ValueError("Укажите оценочную стоимость")

        if self.status in ("ACCEPTED", "REJECTED"):
            if not self.review_comment or not self.review_comment.strip():
                raise ValueError("Комментарий обязателен")

        return self
