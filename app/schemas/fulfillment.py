"""Симуляция заключения кредита: без реальной подписи и движения денег."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class VersionedAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)


class AcceptOfferIn(VersionedAction):
    offer_id: UUID


class FulfillmentOut(BaseModel):
    id: UUID
    status: str
    version: int
    accepted_offer_id: UUID | None
    simulated: bool = True
