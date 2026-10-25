"""Проверка подключения и структуры; ничего не записывает."""
from sqlalchemy import text
from .database import make_engine

def main():
    engine = make_engine()
    try:
        with engine.connect() as c:
            print('База / пользователь:', tuple(c.execute(text('SELECT current_database(),current_user')).one()))
            count = c.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='alfa' AND table_type='BASE TABLE'"))
            if count != 21:
                raise RuntimeError(f'Ожидалась 21 таблица, найдено {count}')
            for row in c.execute(text('SELECT code,name,demo_rate FROM alfa.credit_products ORDER BY code')):
                print(*row)
            print('Подключение и структура: OK; таблиц:', count)
    finally:
        engine.dispose()

if __name__ == '__main__':
    main()
