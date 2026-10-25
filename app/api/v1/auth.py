from datetime import date
import re
from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, status
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from ...core.errors import ApiProblem
from ...core.security import Actor, create_access_token, verify_password
from ...database import get_connection
from ...schemas.auth import LoginRequest, LoginResponse, RegisterRequest

router = APIRouter(prefix='/auth', tags=['Авторизация'])
INDUSTRIES = {'MANUFACTURING', 'TRADE', 'FOOD', 'SERVICES'}


def _email_message(value: str) -> str | None:
    email = value.strip()
    if not email:
        return 'Укажите почту'
    if ' ' in email or email.count('@') != 1:
        return 'В почте должен быть один символ @ и не должно быть пробелов'
    local, domain = email.split('@')
    if not local:
        return 'Укажите имя почты до символа @'
    labels = domain.split('.')
    if len(labels) < 2 or any(not part for part in labels):
        return 'После @ укажите домен с точкой, например company.ru'
    if not re.fullmatch(r'[A-Za-zА-Яа-яЁё]{2,}', labels[-1]):
        return 'После последней точки укажите зону домена, например ru'
    return None


def _issue_token(conn: Connection, email: str) -> LoginResponse:
    user = conn.execute(text("""SELECT id,role,company_id FROM alfa.users
                                WHERE email=:email AND active=true"""), {'email': email}).mappings().first()
    actor = Actor(id=user['id'], role=user['role'], company_id=user['company_id'])
    return LoginResponse(access_token=create_access_token(actor), role=actor.role, company_id=actor.company_id)


@router.post('/register', response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, conn: Connection = Depends(get_connection)):
    message = _email_message(data.email)
    if message:
        raise ApiProblem(422, 'VALIDATION_ERROR', message)
    email = data.email.strip().lower()
    if len(data.password) < 12:
        raise ApiProblem(422, 'VALIDATION_ERROR', 'Пароль должен содержать минимум 12 символов')
    name = data.company_name.strip()
    if not name:
        raise ApiProblem(422, 'VALIDATION_ERROR', 'Укажите название компании')
    inn = data.inn.strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn):
        raise ApiProblem(422, 'VALIDATION_ERROR', 'ИНН должен содержать 10 или 12 цифр')
    if data.industry not in INDUSTRIES:
        raise ApiProblem(422, 'VALIDATION_ERROR', 'Выберите отрасль')
    if conn.execute(text('SELECT 1 FROM alfa.users WHERE email=:email'), {'email': email}).first():
        raise ApiProblem(409, 'EMAIL_TAKEN', 'Кабинет с такой почтой уже есть')
    if conn.execute(text('SELECT 1 FROM alfa.companies WHERE inn=:inn'), {'inn': inn}).first():
        raise ApiProblem(409, 'INN_TAKEN', 'Компания с таким ИНН уже есть')
    try:
        company_id = conn.execute(text("""INSERT INTO alfa.companies(name,inn,industry,registered_at)
            VALUES(:name,:inn,:industry,:registered_at) RETURNING id"""), {
            'name': name, 'inn': inn, 'industry': data.industry, 'registered_at': date.today(),
        }).scalar_one()
        conn.execute(text("""INSERT INTO alfa.users(email,password_hash,role,company_id)
            VALUES(:email,:password_hash,'CLIENT',:company)"""), {
            'email': email, 'password_hash': PasswordHasher().hash(data.password), 'company': company_id,
        })
    except IntegrityError:
        raise ApiProblem(409, 'EMAIL_TAKEN', 'Кабинет с такой почтой уже есть') from None
    return _issue_token(conn, email)


@router.post('/login', response_model=LoginResponse)
def login(data: LoginRequest, conn: Connection = Depends(get_connection)):
    email = data.email.strip().lower()
    user = conn.execute(text("""SELECT id,role,company_id,password_hash FROM alfa.users
                                WHERE email=:email AND active=true"""), {'email': email}).mappings().first()
    if not user or not verify_password(data.password, user['password_hash']):
        raise ApiProblem(401, 'INVALID_CREDENTIALS', 'Неверный email или пароль')
    return _issue_token(conn, email)
