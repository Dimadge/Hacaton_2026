from datetime import date
from decimal import Decimal
from uuid import uuid4
from argon2 import PasswordHasher
from app.config import jwt_secret
from app.main import app
from app.database import get_connection


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, role='CLIENT'):
        self.id = uuid4()
        self.company_id = uuid4() if role == 'CLIENT' else None
        self.role = role
        self.password_hash = PasswordHasher().hash('password-for-testing')
        self.queries = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.queries.append(sql)
        if 'FROM alfa.users' in sql:
            if params.get('email') == 'test@example.test' or params.get('user') == self.id:
                return FakeResult([{
                    'id': self.id, 'role': self.role, 'company_id': self.company_id,
                    'password_hash': self.password_hash,
                }])
            return FakeResult([])
        if 'FROM alfa.companies' in sql:
            return FakeResult([{
                'id': self.company_id, 'name': 'Демо', 'inn': '9912345678',
                'industry': 'TRADE', 'registered_at': date(2023, 1, 1),
            }])
        if 'FROM alfa.credit_products' in sql:
            return FakeResult([{
                'id': uuid4(), 'code': 'INVESTMENT', 'name': 'Инвестиционный',
                'min_amount': Decimal('500000.00'), 'max_amount': Decimal('5000000.00'),
                'min_term': 12, 'max_term': 60, 'demo_rate': Decimal('0.18'),
            }])
        raise AssertionError('Непредвиденный SQL-запрос: '+sql)


def test_login_and_own_company(client, monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'testing-issuer-secret-at-least-32-chars')
    jwt_secret.cache_clear()
    db = FakeDB()
    app.dependency_overrides[get_connection] = lambda: db
    try:
        bad = client.post('/api/v1/auth/login', json={'email': 'test@example.test', 'password': 'bad'})
        assert bad.status_code == 401
        login = client.post('/api/v1/auth/login', json={'email': 'test@example.test',
                                                       'password': 'password-for-testing'})
        assert login.status_code == 200
        assert login.json()['role'] == 'CLIENT'
        headers = {'Authorization': 'Bearer '+login.json()['access_token']}
        company = client.get('/api/v1/me/company', headers=headers)
        assert company.status_code == 200
        assert company.json()['id'] == str(db.company_id)
        assert 'alfa.users' in ' '.join(db.queries)
    finally:
        app.dependency_overrides.clear()
        jwt_secret.cache_clear()


def test_bank_cannot_use_client_company_endpoint(client, monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'testing-issuer-secret-at-least-32-chars')
    jwt_secret.cache_clear()
    db = FakeDB(role='BANK_EMPLOYEE')
    app.dependency_overrides[get_connection] = lambda: db
    try:
        login = client.post('/api/v1/auth/login', json={'email': 'test@example.test',
                                                       'password': 'password-for-testing'})
        assert login.status_code == 200
        company = client.get('/api/v1/me/company', headers={
            'Authorization': 'Bearer '+login.json()['access_token'],
        })
        assert company.status_code == 403
        assert company.json()['code'] == 'FORBIDDEN'
    finally:
        app.dependency_overrides.clear()
        jwt_secret.cache_clear()


def test_products_monetary_fields_as_strings(client):
    app.dependency_overrides[get_connection] = lambda: FakeDB()
    try:
        result = client.get('/api/v1/products')
        assert result.status_code == 200
        assert result.json()[0]['demo_rate'] == '0.18'
        assert result.json()[0]['min_amount'] == '500000.00'
    finally:
        app.dependency_overrides.clear()
