"""BE-09: повторная подача после NEED_INFO; мок SQL-схемы PostgreSQL.

Это не заменяет E2E с реальной PostgreSQL.
"""
from decimal import Decimal
import json
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.core.errors import ApiProblem
from app.core.security import Actor, require_client
from app.main import app
from app.database import get_connection
from app.schemas.application import ApplicationSubmit
from app.services import workflow, checks


class Reply:
    def __init__(self, row=None): self.row = row
    def mappings(self): return self
    def first(self): return self.row


class NeedInfoDB:
    def __init__(self):
        self.app_id=uuid4()
        self.actor=Actor(id=uuid4(), role='CLIENT', company_id=uuid4())
        self.product_id=uuid4()
        self.profile_id=uuid4()
        self.run_id=uuid4()
        self.old_run=uuid4()
        self.state='NEED_INFO'
        self.version=5
        self.money=Decimal('1500000.00')
        self.revenue=Decimal('1000000.00')
        self.key_data={}
        self.runs=[]
        self.transitions=[]
        self.last_snapshot=None
        self.no_rows=False

    def current(self):
        return dict(id=self.app_id,company_id=self.actor.company_id,
            product_id=self.product_id,financial_profile_id=self.profile_id,
            status=self.state,version=self.version,amount=self.money,term=36,
            revenue=self.revenue,expenses=Decimal('600000.00'),
            debt_payments=Decimal('50000.00'),age_months=48,
            cash_reserve=Decimal('300000.00'),document_confirmed=True)

    def execute(self, stmt, params=None):
        sql=str(stmt); params=params or {}
        if 'pg_advisory_xact_lock' in sql: return Reply()
        if 'FROM alfa.idempotency_keys' in sql:
            return Reply(self.key_data.get(params['key']))
        if 'SELECT input_snapshot' in sql and 'FROM alfa.evaluation_runs' in sql:
            return Reply(None if self.no_rows else {
                'input_snapshot': self.last_snapshot or workflow._snapshot(self.current())})
        if 'FROM alfa.credit_products' in sql:
            return Reply(dict(code='INVESTMENT',min_amount=Decimal('500000.00'),
                max_amount=Decimal('5000000.00'),min_term=12,max_term=60,
                demo_rate=Decimal('0.180000')))
        if "set_config('app.actor_id'" in sql:
            return Reply()
        if 'UPDATE alfa.loan_applications' in sql:
            assert params['app']==self.app_id
            assert params['company']==self.actor.company_id
            assert params['version']==self.version
            assert self.state=='NEED_INFO'
            assert "status='NEED_INFO'" in sql
            assert "SET status='CHECKING'" in sql
            self.state='CHECKING'; self.version+=1
            self.transitions.append(('NEED_INFO','CHECKING'))
            return Reply({'version':self.version})
        if 'INSERT INTO alfa.evaluation_runs' in sql:
            assert params['submitted_version']==self.version
            self.last_snapshot=json.loads(params['input_snapshot'])
            self.runs.append({'id': self.run_id, 'snapshot': self.last_snapshot,
                              'submission_version': self.version})
            return Reply({'id':self.run_id})
        if 'INSERT INTO alfa.idempotency_keys' in sql:
            self.key_data[params['key']] = {
                'request_hash':params['request_hash'],
                'response_body':json.loads(params['body'])}
            return Reply()
        raise AssertionError(f'Unexpected SQL: {sql}')


@pytest.fixture
def fake(monkeypatch):
    db=NeedInfoDB()
    monkeypatch.setattr(workflow, 'actor_company',lambda c,u: db.actor.company_id)
    def get_row(conn, actor, app_id, lock=False):
        if actor.company_id != db.actor.company_id or app_id != db.app_id:
            raise ApiProblem(404,'NOT_FOUND','Заявка не найдена')
        return db.current()
    monkeypatch.setattr(workflow,'_get_raw',get_row)
    return db


def test_resubmit_requires_information(fake):
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake,fake.actor,fake.app_id,5)
    assert exc.value.code=='NO_NEW_INFORMATION'
    assert fake.state=='NEED_INFO' and fake.runs==[]


def test_resubmit_with_clarification_creates_new_run_and_single_transition(fake):
    reply=workflow.submit_one(fake,fake.actor,fake.app_id,5,'request-2',
        clarification='Пояснение по просрочке: учебные данные уточнены.')
    assert reply=={'id':str(fake.app_id),'status':'CHECKING',
                   'version':6,'evaluation_run_id':str(fake.run_id)}
    assert fake.transitions==[('NEED_INFO','CHECKING')]
    assert len(fake.runs)==1
    assert fake.runs[0]['submission_version']==6
    assert fake.runs[0]['snapshot']['client_clarification'].startswith('Пояснение')
    assert fake.runs[0]['snapshot']['requested_amount']=='1500000.00'
    assert workflow._hash_request(fake.app_id,5) != workflow._hash_request(fake.app_id,5,'данные')


def test_resubmit_after_changed_financial_fields(fake):
    # Снимок прошлого evaluation_run был создан с прежней выручкой.
    prev=workflow._snapshot(fake.current())
    fake.last_snapshot=prev
    fake.revenue=Decimal('1050000.00')
    reply=workflow.submit_one(fake,fake.actor,fake.app_id,5)
    assert reply['version']==6
    assert fake.runs[0]['snapshot']['monthly_revenue']=='1050000.00'


def test_resubmit_idempotency_and_reuse_key_conflict(fake):
    first=workflow.submit_one(fake,fake.actor,fake.app_id,5,'resubmit-key',
                              clarification='Уточнение сведений для сотрудника банка')
    second=workflow.submit_one(fake,fake.actor,fake.app_id,5,'resubmit-key',
                               clarification='Уточнение сведений для сотрудника банка')
    assert second==first and len(fake.runs)==1 and len(fake.transitions)==1
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake,fake.actor,fake.app_id,5,'resubmit-key',
                            clarification='Другие сведения для сотрудника банка')
    assert exc.value.code=='IDEMPOTENCY_CONFLICT'


def test_resubmit_without_key_after_first_is_conflict(fake):
    workflow.submit_one(fake,fake.actor,fake.app_id,5,
                        clarification='Учебное пояснение для теста')
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake,fake.actor,fake.app_id,5,
                            clarification='Учебное пояснение для теста')
    assert exc.value.code=='VERSION_CONFLICT'


def test_resubmit_rejects_missing_prior_run(fake):
    fake.no_rows=True
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake,fake.actor,fake.app_id,5,
                            clarification='Учебное пояснение для теста')
    assert exc.value.code=='NO_EVALUATION'


def test_resubmit_rejects_other_company(fake):
    stranger=Actor(id=uuid4(),role='CLIENT',company_id=uuid4())
    with pytest.raises(ApiProblem) as exc:
        workflow.submit_one(fake,stranger,fake.app_id,5,
                            clarification='Учебное пояснение для теста')
    assert exc.value.status_code==404


@pytest.mark.parametrize('clarification',[" ","мало", "x"*2001])
def test_clarification_validation(clarification):
    with pytest.raises(ValidationError):
        ApplicationSubmit(version=5,clarification=clarification)


def test_api_resubmit_with_mock_checks(client, fake, monkeypatch):
    seen=[]
    monkeypatch.setattr(checks,'ensure_checks',lambda conn,actor,app_id: seen.append(app_id))
    app.dependency_overrides[require_client]=lambda: fake.actor
    app.dependency_overrides[get_connection]=lambda: fake
    try:
        r=client.post(f'/api/v1/applications/{fake.app_id}/submit',
            json={'version':5,'clarification':'Дополнены сведения о просрочке'},
            headers={'Idempotency-Key':'resubmit-api'})
        assert r.status_code==200,r.text
        assert r.json()['status']=='CHECKING' and r.json()['version']==6
        assert seen==[fake.app_id]
    finally:
        app.dependency_overrides.clear()


def test_openapi_has_resubmit_and_bank_clarification(client):
    schemas=client.get('/openapi.json').json()['components']['schemas']
    assert 'clarification' in schemas['ApplicationSubmit']['properties']
    assert 'client_clarification' in schemas['BankApplicationOut']['properties']
