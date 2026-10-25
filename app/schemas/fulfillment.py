"""Симуляция заключения кредита: без реальной подписи и движения денег."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class VersionedAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)


class AcceptOfferIn(VersionedAction):
    offer_id: UUID


class SignWithCodeIn(VersionedAction):
    code: str = Field(pattern=r"^[0-9]{6}$")


class SignCodeOut(BaseModel):
    expires_in_seconds: int
    demo_code: str


class FulfillmentOut(BaseModel):
    id: UUID
    status: str
    version: int
    accepted_offer_id: UUID | None
    simulated: bool = True
