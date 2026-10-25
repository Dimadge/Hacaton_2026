"""BE-06: контракт результатов mock ФНС и БКИ для Frontend / Backend."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class VerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    run_id: UUID
    source: Literal['FNS', 'BKI']
    result: str
    payload: dict[str, Any]
    checked_at: datetime


class ChecksOut(BaseModel):
    application_id: UUID
    evaluation_run_id: UUID | None
    application_status: str
    completed: bool
    checks: list[VerificationOut]
    reason_codes: list[str]
    # completed=True означает лишь, что обе mock-проверки записаны,
    # а НЕ то, что заявка одобрена или рассчитан скоринг.
