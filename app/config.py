"""Настройки бэкенда. Секреты никогда не выводятся в логи."""
import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)


def required(name: str) -> str:
    value = os.getenv(name, '')
    if not value or value.startswith('CHANGE_ME'):
        raise ValueError(f'Задайте {name} в .env или переменных окружения')
    return value


def database_url(admin: bool = False) -> URL:
    return URL.create(
        'postgresql+psycopg',
        username=required('POSTGRES_USER' if admin else 'DB_USER'),
        password=required('POSTGRES_PASSWORD' if admin else 'DB_PASSWORD'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', os.getenv('POSTGRES_PORT', '5432'))),
        database=required('POSTGRES_DB'),
    )


@lru_cache
def jwt_secret() -> str:
    secret = required("JWT_SECRET")
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("JWT_SECRET должен содержать минимум 32 байта")
    return secret
