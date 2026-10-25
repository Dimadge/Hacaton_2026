from uuid import UUID
from pydantic import BaseModel


class LoginRequest(BaseModel):
    # EmailStr требует отдельного пакета email-validator; простой str проверим вручную.
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    company_name: str
    inn: str
    phone: str
    director_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    role: str
    company_id: UUID | None
