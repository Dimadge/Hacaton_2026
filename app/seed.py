"""Идемпотентное наполнение базы синтетическими демо-учётками.

Запуск в Docker: docker compose run --rm seed
Банк/клиенты создаются только при отсутствии, существующие пароли не перезаписываются.
"""
from datetime import date
from argon2 import PasswordHasher
from sqlalchemy import text
from .config import required
from .database import make_engine

CLIENTS = (
    ('client_good', '9912345601', 'Демо: Мастерская', 'MANUFACTURING', 'active', 'good'),
    ('client_alternative', '9912345602', 'Демо: Оборудование', 'MANUFACTURING', 'active', 'good'),
    ('client_manual', '9912345603', 'Демо: Магазин', 'TRADE', 'active', 'minor_delay'),
    ('client_missing', '9912345604', 'Демо: Кафе', 'FOOD', 'active', 'good'),
    ('client_reject', '9912345605', 'Демо: Сервис', 'SERVICES', 'active', 'critical'),
)


def main():
    # При запуске по умолчанию используем отдельные секреты из .env, не публикуем их.
    client_password = required('DEMO_CLIENT_PASSWORD')
    bank_password = required('DEMO_BANK_PASSWORD')
    if min(len(client_password), len(bank_password)) < 12:
        raise ValueError('Демо-пароли должны содержать не менее 12 символов')
    hasher = PasswordHasher()
    engine = make_engine(admin=True)
    try:
        with engine.begin() as conn:
            for code, inn, name, industry, fns, bki in CLIENTS:
                conn.execute(text("""INSERT INTO alfa.companies(name,inn,industry,registered_at)
                    VALUES (:name,:inn,:industry,:registered_at)
                    ON CONFLICT(inn) DO NOTHING"""), {
                    'name': name, 'inn': inn, 'industry': industry, 'registered_at': date(2023, 1, 1),
                })
                company = conn.scalar(text('SELECT id FROM alfa.companies WHERE inn=:inn'), {'inn': inn})
                conn.execute(text("""INSERT INTO alfa.users(email,password_hash,role,company_id)
                    VALUES(:email,:password_hash,'CLIENT',:company)
                    ON CONFLICT(email) DO NOTHING"""), {
                    'email': f'{code}@example.test',
                    'password_hash': hasher.hash(client_password), 'company': company,
                })
                conn.execute(text("""INSERT INTO alfa.mock_profiles
                    (company_id,registry_flag,credit_history_flag)
                    VALUES(:company,:fns,:bki) ON CONFLICT(company_id) DO NOTHING"""), {
                    'company': company, 'fns': fns, 'bki': bki,
                })
            conn.execute(text("""INSERT INTO alfa.users(email,password_hash,role,company_id)
                VALUES ('bank@example.test',:hash,'BANK_EMPLOYEE',NULL)
                ON CONFLICT(email) DO NOTHING"""), {'hash': hasher.hash(bank_password)})
        print('Демо-данные подготовлены: 5 клиентов + 1 сотрудник.')
        print('Email клиентов: client_good@example.test, client_alternative@example.test,')
        print('  client_manual@example.test, client_missing@example.test, client_reject@example.test')
        print('Email сотрудника: bank@example.test')
        print('Пароли заданы в .env и не печатаются.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
