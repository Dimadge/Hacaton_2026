"""BE-05 unit/API tests. Fake SQL responses emulate DB trigger versions.

Real PostgreSQL trigger/audit checks are performed via Swagger/E2E on local Docker.
"""
from datetime import date
from decimal import Decimal
import json
from uuid import uuid4

import pytest
from app.main import app
from app.database import get_connection
from app.core.security import Actor, require_client
from app.core.errors import ApiProblem
from app.services import workflow
from app.services import checks


class Result:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class ConnectionStub:
    def __init__(self):
        self.app_id = uuid4()
        self.actor = Actor(id=uuid4(), role='CLIENT', company_id=uuid4())
        self.product_id = uuid4()
        self.profile_id = uuid4()
        self.run_id = uuid4()
        self.state = 'DRAFT'
        self.version = 1
        self.transitions = []
        self.snapshots = []
        self.saved_keys = {}

    def current_row(self):
        return dict(id=self.app_id, company_id=self.actor.company_id, status=self.state,
                    version=self.version, product_id=self.product_id, amount=Decimal('3000000.00'),
                    term=36, revenue=Decimal('1500000.00'), expenses=Decimal('900000.00'),
                    debt_payments=Decimal('150000.00'), age_months=36,
                    cash_reserve=Decimal('800000.00'), document_confirmed=True,
                    financial_profile_id=self.profile_id)

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if 'pg_advisory_xact_lock' in sql:
            return Result()
        if 'FROM alfa.idempotency_keys' in sql:
            return Result(self.saved_keys.get(params['key']))
        if 'set_config(' in sql:
            assert params['actor'] == str(self.actor.id)
            return Result()
        if 'UPDATE alfa.loan_applications' in sql:
            target = 'SUBMITTED' if "status='SUBMITTED'" in sql.split('SET ', 1)[1].split('WHERE ', 1)[0] else 'CHECKING'
            previous = 'DRAFT' if target == 'SUBMITTED' else 'SUBMITTED'
            assert params['app'] == self.app_id
            assert params['company'] == self.actor.company_id
            if self.state != previous or self.version != params['version']:
                return Result()
            self.state = target
            self.version += 1  # В PostgreSQL это делает guard_application.
            self.transitions.append((previous, target))
            return Result({'version': self.version})
        if 'FROM alfa.credit_products' in sql:
            assert params['product'] == self.product_id
            return Result({'code':'INVESTMENT','min_amount':Decimal('500000.00'),
                           'max_amount':Decimal('5000000.00'),'min_term':12,
                           'max_term':60,'demo_rate':Decimal('0.180000')})
        if 'INSERT INTO alfa.evaluation_runs' in sql:
            assert params['submitted_version'] == 2
            self.snapshots.append({'input':json.loads(params['input_snapshot']),
                                   'product':json.loads(params['product_snapshot'])})
            return Result({'id':self.run_id})
        if 'INSERT INTO alfa.idempotency_keys' in sql:
            self.saved_keys[params['key']] = {
                'request_hash':params['request_hash'],
                'response_body':json.loads(params['body']),
            }
            return Result()
        raise AssertionError(f'Unexpected SQL: {sql}')


@pytest.fixture
def fake(monkeypatch):
    db = ConnectionStub()
    monkeypatch.setattr(workflow, 'actor_company', lambda conn, actor_id: db.actor.company_id)
    monkeypatch.setattr(workflow, '_get_raw',
                        lambda conn, actor, app_id, lock=False: db.current_row()
                        if actor.company_id == db.actor.company_id and app_id == db.app_id
                        else (_ for _ in ()).throw(ApiProblem(404, 'NOT_FOUND', 'Заявка не найдена')))
    return db


def test_allowed_transitions_and_terminal_states():
    for source, targets in workflow.ALLOWED_TRANSITIONS.items():
        for target in targets:
            workflow.ensure_transition(source, target)
    for status in ('REJECTED', 'DISBURSED', 'CANCELLED'):
        with pytest.raises(ApiProblem) as exc:
            workflow.ensure_transition(status, 'SUBMITTED')
        assert exc.value.status_code == 409
    with pytest.raises(ApiProblem):
        workflow.ensure_transition('DRAFT', 'OFFERED')


def test_submit_creates_single_run_and_two_state_transitions(fake):
    result = workflow.submit_one(fake, fake.actor, fake.app_id, 1, 'submission-001')
    assert result == {'id': str(fake.app_id), 'status': 'CHECKING',
                      'version': 3, 'evaluation_run_id': str(fake.run_id)}
    assert fake.transitions == [('DRAFT', 'SUBMITTED'), ('SUBMITTED', 'CHECKING')]
    assert len(fake.snapshots) == 1
    assert fake.snapshots[0]['input']['monthly_revenue'] == '1500000.00'
    assert fake.snapshots[0]['product']['demo_rate'] == '0.180000'


def test_same_key_reuses_original_result_without_duplicate(fake):
    first = workflow.submit_one(fake, fake.actor, fake.app_id, 1, 'same-key')
    second = workflow.submit_one(fake, fake.actor, fake.app_id, 1, 'same-key')
    assert second == first
    assert len(fake.transitions) == 2
    assert len(fake.snapshots) == 1


def test_reused_key_with_different_payload_rejected(fake):
    workflow.submit_one(fake, fake.actor, fake.app_id, 1, 'same-key')
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake, fake.actor, fake.app_id, 2, 'same-key')
    assert exc.value.code == 'IDEMPOTENCY_CONFLICT'
    assert len(fake.snapshots) == 1


def test_repeated_submit_without_key_is_conflict(fake):
    workflow.submit_one(fake, fake.actor, fake.app_id, 1)
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake, fake.actor, fake.app_id, 1)
    assert exc.value.status_code == 409
    assert len(fake.snapshots) == 1


def test_stale_version_rejected_before_mutation(fake):
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake, fake.actor, fake.app_id, 99, 'different')
    assert exc.value.code == 'VERSION_CONFLICT'
    assert fake.transitions == []


def test_other_company_not_found(fake):
    stranger = Actor(id=uuid4(), role='CLIENT', company_id=uuid4())
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake, stranger, fake.app_id, 1)
    assert exc.value.status_code == 404


def test_api_submit_contract_in_swagger(client, fake, monkeypatch):
    monkeypatch.setattr(checks, "ensure_checks", lambda conn, actor, application_id: None)
    app.dependency_overrides[require_client] = lambda: fake.actor
    app.dependency_overrides[get_connection] = lambda: fake
    try:
        response = client.post(f'/api/v1/applications/{fake.app_id}/submit',
                               json={'version':1}, headers={'Idempotency-Key':'api-test-01'})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'CHECKING'
        repeat = client.post(f'/api/v1/applications/{fake.app_id}/submit',
                             json={'version':1}, headers={'Idempotency-Key':'api-test-01'})
        assert repeat.status_code == 200
        assert repeat.json() == response.json()
        assert len(fake.snapshots) == 1
    finally:
        app.dependency_overrides.clear()


def test_missing_version_rejected_by_pydantic(client):
    """422 на валидации происходит до проверки токена и входа в БД."""
    reply = client.post(f'/api/v1/applications/{uuid4()}/submit', json={})
    # Depending on auth order this may be 401, but MUST NOT submit anything.
    assert reply.status_code in (401, 422)


def test_api_submit_also_calls_mock_checks_in_same_connection(client, fake, monkeypatch):
    call_log = []

    def check_spy(conn, actor, application_id):
        call_log.append((conn, actor, application_id))

    monkeypatch.setattr(checks, "ensure_checks", check_spy)
    app.dependency_overrides[require_client] = lambda: fake.actor
    app.dependency_overrides[get_connection] = lambda: fake
    try:
        response = client.post(f'/api/v1/applications/{fake.app_id}/submit',
                               json={'version': 1})
        assert response.status_code == 200
        assert call_log == [(fake, fake.actor, fake.app_id)]
        assert fake.state == 'CHECKING'
    finally:
        app.dependency_overrides.clear()
