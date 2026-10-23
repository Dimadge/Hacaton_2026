"""Единый SQLAlchemy engine и одна транзакция на HTTP-запрос.

Структура таблиц описана существующими db/init/*.sql, ORM их не пересоздаёт.
"""
from functools import lru_cache
from typing import Iterator
from sqlalchemy import Connection, create_engine, Engine
from .config import database_url


def make_engine(admin: bool = False) -> Engine:
    return create_engine(
        database_url(admin),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={'connect_timeout': 5, 'options': '-c timezone=UTC'},
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine()


def get_connection() -> Iterator[Connection]:
    # rollback при исключении; commit при успешном HTTP-запросе.
    with get_engine().begin() as conn:
        yield conn
