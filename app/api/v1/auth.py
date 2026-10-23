from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text
from ...core.errors import ApiProblem
from ...core.security import Actor, create_access_token, verify_password
from ...database import get_connection
from ...schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix='/auth', tags=['Авторизация'])


@router.post('/login', response_model=LoginResponse)
def login(data: LoginRequest, conn: Connection = Depends(get_connection)):
    email = data.email.strip().lower()
    user = conn.execute(text("""SELECT id,role,company_id,password_hash FROM alfa.users
                                WHERE email=:email AND active=true"""), {'email': email}).mappings().first()
    if not user or not verify_password(data.password, user['password_hash']):
        raise ApiProblem(401, 'INVALID_CREDENTIALS', 'Неверный email или пароль')
    actor = Actor(id=user['id'], role=user['role'], company_id=user['company_id'])
    return LoginResponse(access_token=create_access_token(actor), role=actor.role, company_id=actor.company_id)
