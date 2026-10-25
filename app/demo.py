"""Ручной пример записи синтетического клиента и черновика; не тесты.
Запуск повторно создаёт нового клиента с другим демонстрационным ИНН.
"""
from datetime import date
from getpass import getpass
import secrets
from .database import make_engine
from .repository import register_new_company, create_draft, add_month, list_my_applications

def main():
    password = getpass('Пароль нового демо-клиента (минимум 12 символов): ')
    inn = '99' + ''.join(secrets.choice('0123456789') for _ in range(8))
    email = f'demo-{inn}@example.invalid'
    engine = make_engine()
    try:
        with engine.begin() as conn:
            user, company = register_new_company(conn,email=email,password=password,
                name='ДЕМО: Мастерская',inn=inn,industry='MANUFACTURING',registered_at=date(2023,1,1))
            app, profile = create_draft(conn,actor_id=user,product_code='INVESTMENT',
                amount='3000000',term=36,purpose='Покупка оборудования',
                revenue='1500000',expenses='900000',debt_payments='150000',
                age_months=36,cash_reserve='800000')
            add_month(conn,actor_id=user,profile_id=profile,month=date(2026,9,1),
                      revenue='1500000',expenses='900000')
            rows = list_my_applications(conn,user)
        print('Сохранено. Email:',email,'User:',user,'Company:',company)
        for row in rows: print(dict(row))
        print('Скоринг не запускался; заявка осталась DRAFT.')
    finally:
        engine.dispose()

if __name__ == '__main__':
    main()
