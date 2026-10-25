"""Примеры параметризованных запросов; не готовый HTTP API.
actor_id должен приходить из проверенной сервером сессии, не из тела запроса.
"""
from decimal import Decimal
from sqlalchemy import text
from argon2 import PasswordHasher

class AccessDenied(ValueError):
    pass

def actor_company(conn, actor_id):
    company = conn.scalar(text("SELECT company_id FROM alfa.users WHERE id=:id AND role='CLIENT' AND active"), {'id':actor_id})
    if company is None:
        raise AccessDenied('Требуется активный CLIENT')
    conn.execute(text("SELECT set_config('app.actor_id', :actor, true)"), {'actor':str(actor_id)})
    return company

def register_new_company(conn, *, email, password, name, inn, industry, registered_at):
    # По известному ИНН не присоединяем пользователя: требуется подтверждение доступа.
    if conn.scalar(text('SELECT id FROM alfa.companies WHERE inn=:inn'), {'inn':inn}):
        raise ValueError('Компания уже есть: требуется приглашение/подтверждение доступа')
    if len(password) < 12:
        raise ValueError('Пароль должен содержать минимум 12 символов')
    company = conn.scalar(text("""INSERT INTO alfa.companies(name,inn,industry,registered_at)
        VALUES(:name,:inn,:industry,:date) RETURNING id"""),
        {'name':name,'inn':inn,'industry':industry,'date':registered_at})
    user = conn.scalar(text("""INSERT INTO alfa.users(email,password_hash,role,company_id)
        VALUES(:email,:hash,'CLIENT',:company) RETURNING id"""),
        {'email':email.strip().lower(),'hash':PasswordHasher().hash(password),'company':company})
    return user, company

def create_draft(conn, *, actor_id, product_code, amount, term, purpose,
                 revenue, expenses, debt_payments, age_months, cash_reserve=None, document_confirmed=False):
    company = actor_company(conn, actor_id)
    # Денежные значения передавайте Decimal или строками, никогда float.
    for v in (amount,revenue,expenses,debt_payments,cash_reserve):
        if v is not None and isinstance(v, float):
            raise ValueError('Деньги передавайте строкой или Decimal')
    product = conn.scalar(text('SELECT id FROM alfa.credit_products WHERE code=:code AND active'), {'code':product_code})
    if product is None:
        raise ValueError('Продукт не найден')
    application = conn.scalar(text("""INSERT INTO alfa.loan_applications
        (company_id,created_by,product_id,amount,term,purpose)
        VALUES(:company,:actor,:product,:amount,:term,:purpose) RETURNING id"""),
        {'company':company,'actor':actor_id,'product':product,'amount':Decimal(amount),'term':term,'purpose':purpose})
    profile = conn.scalar(text("""INSERT INTO alfa.financial_profiles
        (application_id,revision,revenue,expenses,debt_payments,age_months,cash_reserve,document_confirmed)
        VALUES(:app,1,:revenue,:expenses,:debt,:age,:reserve,:confirmed) RETURNING id"""),
        {'app':application,'revenue':Decimal(revenue),'expenses':Decimal(expenses),
         'debt':Decimal(debt_payments),'age':age_months,
         'reserve':None if cash_reserve is None else Decimal(cash_reserve),
         'confirmed': document_confirmed})
    return application, profile

def list_my_applications(conn, actor_id):
    company = actor_company(conn, actor_id)
    return conn.execute(text("""SELECT id,amount,term,status,version,created_at
        FROM alfa.loan_applications WHERE company_id=:company ORDER BY created_at DESC"""),
        {'company':company}).mappings().all()

def add_month(conn, *, actor_id, profile_id, month, revenue, expenses):
    company = actor_company(conn, actor_id)
    row = conn.execute(text("""SELECT a.id,a.status FROM alfa.loan_applications a
       JOIN alfa.financial_profiles p ON p.application_id=a.id
       WHERE p.id=:profile AND a.company_id=:company FOR UPDATE OF a"""),
       {'profile':profile_id,'company':company}).first()
    if row is None:
        raise AccessDenied('Анкета недоступна')
    if row.status not in ('DRAFT','NEED_INFO'):
        raise ValueError('Анкета уже отправлена')
    if conn.scalar(text('SELECT 1 FROM alfa.evaluation_runs WHERE financial_profile_id=:p LIMIT 1'), {'p':profile_id}):
        raise ValueError('Создайте новую версию анкеты: предыдущая уже использована')
    for v in (revenue, expenses):
        if isinstance(v,float): raise ValueError('Используйте Decimal или строку')
    conn.execute(text("""INSERT INTO alfa.monthly_financials(financial_profile_id,month,revenue,expenses)
        VALUES(:profile,:month,:revenue,:expenses)"""),
        {'profile':profile_id,'month':month,'revenue':Decimal(revenue),'expenses':Decimal(expenses)})
