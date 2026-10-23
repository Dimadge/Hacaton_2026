"""Настройки из .env в корне проекта. Пароли не выводим в логи."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)

def required(name):
    value = os.getenv(name, '')
    if not value or value.startswith('CHANGE_ME'):
        raise ValueError(f'Задайте {name} в .env')
    return value

def database_url(admin=False):
    return URL.create(
        'postgresql+psycopg',
        username=required('POSTGRES_USER' if admin else 'DB_USER'),
        password=required('POSTGRES_PASSWORD' if admin else 'DB_PASSWORD'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=required('POSTGRES_DB'),
    )
