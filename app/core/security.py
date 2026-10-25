"""JWT-сессии. Роль в токене не заменяет повторную проверку роли и active в БД."""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID
import jwt
from jwt import InvalidTokenError
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import Connection, text
from ..config import jwt_secret
from ..database import get_connection
from .errors import ApiProblem

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)


class Actor(BaseModel):
    id: UUID
    role: str
    company_id: UUID | None


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(actor: Actor) -> str:
    now = datetime.now(timezone.utc)
    minutes = int(os.getenv('JWT_EXPIRE_MINUTES', '120'))
    if not 1 <= minutes <= 1440:
        raise ValueError('JWT_EXPIRE_MINUTES вне допустимого диапазона 1..1440')
    payload = {
        'sub': str(actor.id), 'iat': now,
        'exp': now + timedelta(minutes=minutes),
        'iss': 'alfa-navigator-demo',
        'type': 'access',
    }
    return jwt.encode(payload, jwt_secret(), algorithm='HS256')


def decode_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UUID:
    # Выполняется ДО подключения к БД: без токена отвечаем 401 без SQL.
    if credentials is None:
        raise ApiProblem(401, 'UNAUTHORIZED', 'Необходимо войти в систему')
    try:
        payload = jwt.decode(
            credentials.credentials, jwt_secret(), algorithms=['HS256'],
            issuer='alfa-navigator-demo', options={'require': ['sub', 'exp', 'iat', 'iss']},
        )
        if payload.get('type') != 'access':
            raise InvalidTokenError('Неверный тип токена')
        return UUID(payload['sub'])
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise ApiProblem(401, 'UNAUTHORIZED', 'Сессия недействительна или истекла') from None


def get_current_user(
    user_id: UUID = Depends(decode_access_token),
    conn: Connection = Depends(get_connection),
) -> Actor:
    user = conn.execute(text("""SELECT id,role,company_id FROM alfa.users
                                WHERE id=:user AND active=true"""), {'user': user_id}).mappings().first()
    if user is None:
        raise ApiProblem(401, 'UNAUTHORIZED', 'Аккаунт недоступен')
    return Actor(**user)


def require_client(actor: Actor = Depends(get_current_user)) -> Actor:
    if actor.role != 'CLIENT' or actor.company_id is None:
        raise ApiProblem(403, 'FORBIDDEN', 'Доступно только предпринимателю')
    return actor


def require_bank_employee(actor: Actor = Depends(get_current_user)) -> Actor:
    if actor.role != 'BANK_EMPLOYEE':
        raise ApiProblem(403, 'FORBIDDEN', 'Доступно только сотруднику банка')
    return actor
