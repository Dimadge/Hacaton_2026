from uuid import uuid4
from app.main import app
from app.database import get_connection
from app.core.security import require_client, Actor


def test_health_is_public(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'service': 'alfa-navigator-api'}
    assert 'X-Request-ID' in response.headers


def test_openapi_has_expected_api(client):
    response = client.get('/openapi.json')
    assert response.status_code == 200
    paths = response.json()['paths']
    for path in ('/api/v1/auth/login', '/api/v1/products', '/api/v1/me/company',
                 '/api/v1/applications', '/api/v1/applications/{application_id}'):
        assert path in paths


def test_invalid_money_float_rejected(client):
    app.dependency_overrides[get_connection] = lambda: None
    app.dependency_overrides[require_client] = lambda: Actor(
        id=uuid4(), role='CLIENT', company_id=uuid4())
    try:
        response = client.post('/api/v1/applications', json={
            'product_code': 'INVESTMENT', 'purpose': 'Покупка оборудования',
            'requested_amount': 3000000.0, 'term_months': 36,
            'financials': {'monthly_revenue': '1500000', 'operating_expenses': '900000',
                           'existing_debt_payments': '150000', 'business_age_months': 36},
        })
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert response.json()['code'] == 'VALIDATION_ERROR'


def test_auth_required(client):
    response = client.get('/api/v1/applications')
    assert response.status_code == 401
    assert response.json()['code'] == 'UNAUTHORIZED'
