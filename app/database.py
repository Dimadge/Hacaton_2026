"""SQLAlchemy Core: SQL-схема — единственный источник структуры.
engine.begin() фиксирует транзакцию при успехе, откатывает при исключении.
Для будущего FastAPI создавайте engine один раз на процесс.
"""
from sqlalchemy import create_engine
from .config import database_url

def make_engine(admin=False):
    return create_engine(database_url(admin), pool_pre_ping=True,
                         hide_parameters=True,
                         connect_args={'connect_timeout': 5,
                                       'options': '-c timezone=UTC'})
