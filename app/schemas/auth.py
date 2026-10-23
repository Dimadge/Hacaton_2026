from uuid import UUID
from pydantic import BaseModel


class LoginRequest(BaseModel):
    # EmailStr требует отдельного пакета email-validator; простой str проверим вручную.
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    role: str
    company_id: UUID | None
