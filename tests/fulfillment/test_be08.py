from datetime import datetime, timedelta, timezone
"""BE-08 unit/route tests. PostgreSQL trigger behavior still needs real E2E."""
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.core.errors import ApiProblem
from app.core.security import Actor, require_client, require_bank_employee
from app.database import get_connection
from app.schemas.fulfillment import AcceptOfferIn, VersionedAction, SignWithCodeIn
from app.services import fulfillment


class FakeResult:
    def __init__(self, row=None): self.row = row
    def mappings(self): return self
    def first(self): return self.row


class FakeDB:
    def __init__(self, status='OFFERED', version=4):
        self.app_id, self.offer_id, self.decision_id = uuid4(),uuid4(),uuid4()
        self.company_id, self.user_id = uuid4(), uuid4()
        self.actor = Actor(id=self.user_id, company_id=self.company_id, role='CLIENT')
        self.status,self.version,self.accepted_offer_id=status,version,None
        self.event_history=[]
        self.decisions_found=True
        self.existing_offer=True
        self.offer_is_latest=True
        self.simulate_conflict=False
        self.sign_codes = {}
    def execute(self, statement, params=None):
        sql = str(statement); params = params or {}
        if "set_config('app.actor_id'" in sql:
            assert params['actor']==str(self.user_id)
            return FakeResult()
        if 'FROM alfa.credit_offers o' in sql:
            return FakeResult({'id':self.offer_id,'decision_id':self.decision_id}
                              if self.existing_offer and params['offer']==self.offer_id else None)
        if 'FROM alfa.credit_decisions d' in sql:
            return FakeResult({'id':self.decision_id if self.offer_is_latest else uuid4()}
                              if self.decisions_found else None)
        if 'FROM alfa.signing_codes' in sql:
            return FakeResult(self.sign_codes or None)
        if 'INSERT INTO alfa.signing_codes' in sql:
            self.sign_codes = {
                'code_hash': params['digest'], 'salt': params['salt'],
                'expires_at': params['expires'], 'requested_at': params['requested'],
                'attempts': 0, 'used_at': None,
            }
            return FakeResult()
        if 'UPDATE alfa.signing_codes' in sql:
            if 'attempts = attempts + 1' in sql:
                self.sign_codes['attempts'] += 1
            if 'used_at = now()' in sql:
                self.sign_codes['used_at'] = datetime.now(timezone.utc)
            return FakeResult()
        if 'UPDATE alfa.loan_applications' in sql:
            assert params['app']==self.app_id and params['company']==self.company_id
            if self.simulate_conflict: return FakeResult(None)
            assert params['version']==self.version and params['source']==self.status
            previous=self.status
            self.status=params['target']; self.version+=1
            if params['offer'] is not None: self.accepted_offer_id=params['offer']
            self.event_history.append((previous,self.status,self.version))
            return FakeResult({'version':self.version,'accepted_offer_id':self.accepted_offer_id})
        raise AssertionError('Unexpected SQL: '+sql)


def lock_fake(monkeypatch, db):
    def get_row(_conn, actor, app_id, lock=False):
        if app_id!=db.app_id or actor.company_id!=db.company_id:
            raise ApiProblem(404,'NOT_FOUND','Заявка не найдена')
        assert lock
        return {'id':app_id,'status':db.status,'version':db.version}
    monkeypatch.setattr(fulfillment,'_get_raw',get_row)


def test_full_happy_flow(monkeypatch):
    db=FakeDB(); lock_fake(monkeypatch,db)
    accepted=fulfillment.accept_offer(db,db.actor,db.app_id,4,db.offer_id)
    assert accepted=={'id':db.app_id,'status':'ACCEPTED','version':5,
                      'accepted_offer_id':db.offer_id,'simulated':True}
    otp=fulfillment.request_signing_code(db,db.actor,db.app_id,5)
    signed=fulfillment.sign_application(db,db.actor,db.app_id,5,otp['demo_code'])
    assert signed['status']=='SIGNED' and signed['version']==6
    disbursed=fulfillment.simulate_disbursement(db,db.actor,db.app_id,6)
    assert disbursed['status']=='DISBURSED' and disbursed['version']==7
    assert disbursed['accepted_offer_id']==db.offer_id
    assert db.event_history==[('OFFERED','ACCEPTED',5),('ACCEPTED','SIGNED',6),
                              ('SIGNED','DISBURSED',7)]
    with pytest.raises(ApiProblem) as err:
        fulfillment.simulate_disbursement(db,db.actor,db.app_id,7)
    assert err.value.code=='INVALID_STATE_TRANSITION'


def test_cancel_is_terminal(monkeypatch):
    db=FakeDB(); lock_fake(monkeypatch,db)
    response=fulfillment.cancel_offer(db,db.actor,db.app_id,4)
    assert response['status']=='CANCELLED' and response['accepted_offer_id'] is None
    with pytest.raises(ApiProblem):
        fulfillment.accept_offer(db,db.actor,db.app_id,5,db.offer_id)


@pytest.mark.parametrize('state,expected',[
    ('DRAFT','INVALID_STATE_TRANSITION'),('CHECKING','INVALID_STATE_TRANSITION'),
    ('ACCEPTED','INVALID_STATE_TRANSITION'),('SIGNED','INVALID_STATE_TRANSITION'),
    ('DISBURSED','INVALID_STATE_TRANSITION'),('REJECTED','INVALID_STATE_TRANSITION'),
    ('NEED_INFO','INVALID_STATE_TRANSITION')])
def test_accept_from_wrong_state(monkeypatch,state,expected):
    db=FakeDB(status=state);lock_fake(monkeypatch,db)
    with pytest.raises(ApiProblem) as err:
        fulfillment.accept_offer(db,db.actor,db.app_id,4,db.offer_id)
    assert err.value.code==expected
    assert not db.event_history


def test_wrong_offer_id(monkeypatch):
    db=FakeDB();lock_fake(monkeypatch,db)
    with pytest.raises(ApiProblem) as err:
        fulfillment.accept_offer(db,db.actor,db.app_id,4,uuid4())
    assert err.value.status_code==404
    assert db.status=='OFFERED'


def test_stale_offer(monkeypatch):
    db=FakeDB();db.offer_is_latest=False;lock_fake(monkeypatch,db)
    with pytest.raises(ApiProblem) as err:
        fulfillment.accept_offer(db,db.actor,db.app_id,4,db.offer_id)
    assert err.value.code=='STALE_OFFER'


def test_version_conflict(monkeypatch):
    db=FakeDB();lock_fake(monkeypatch,db)
    with pytest.raises(ApiProblem) as err:
        fulfillment.accept_offer(db,db.actor,db.app_id,3,db.offer_id)
    assert err.value.code=='VERSION_CONFLICT'
    assert not db.event_history


def test_racing_update_conflict(monkeypatch):
    db=FakeDB();db.simulate_conflict=True;lock_fake(monkeypatch,db)
    with pytest.raises(ApiProblem) as err:
        fulfillment.accept_offer(db,db.actor,db.app_id,4,db.offer_id)
    assert err.value.code=='VERSION_CONFLICT'


def test_company_isolation(monkeypatch):
    db=FakeDB();lock_fake(monkeypatch,db)
    other=Actor(id=uuid4(), role='CLIENT',company_id=uuid4())
    with pytest.raises(ApiProblem) as err:
        fulfillment.accept_offer(db,other,db.app_id,4,db.offer_id)
    assert err.value.status_code==404


@pytest.mark.parametrize('payload', [{'version':0},{'version':1,'extra':'bad'},
                                      {'version':'foo'},{'version':-1}])
def test_schema_rejects_invalid_versions(payload):
    with pytest.raises(ValidationError): VersionedAction.model_validate(payload)


def test_schema_rejects_bad_offer():
    with pytest.raises(ValidationError): AcceptOfferIn(version=2,offer_id='not-a-uuid')


def test_routes_present():
    schema=app.openapi()['paths']
    for endpoint in ('accept','sign','disburse','cancel'):
        path=f'/api/v1/applications/{{application_id}}/{endpoint}'
        assert 'post' in schema[path]
        assert 'requestBody' in schema[path]['post']


def test_fastapi_client_flow(monkeypatch):
    db=FakeDB();lock_fake(monkeypatch,db)
    app.dependency_overrides[require_client]=lambda: db.actor
    app.dependency_overrides[get_connection]=lambda: db
    try:
        with TestClient(app) as http:
            r=http.post(f'/api/v1/applications/{db.app_id}/accept',json={
                'version':4,'offer_id':str(db.offer_id)})
            assert r.status_code==200,r.text
            assert r.json()['status']=='ACCEPTED'
            code=http.post(f'/api/v1/applications/{db.app_id}/sign/code',json={'version':5})
            assert code.status_code==200,code.text
            r=http.post(f'/api/v1/applications/{db.app_id}/sign',json={
                'version':5,'code':code.json()['demo_code']})
            assert r.status_code==200,r.text
            r=http.post(f'/api/v1/applications/{db.app_id}/disburse',json={'version':6})
            assert r.status_code==200,r.text
            assert r.json()['status']=='DISBURSED'
            r=http.post(f'/api/v1/applications/{db.app_id}/disburse',json={'version':7})
            assert r.status_code==409,r.text
    finally:
        app.dependency_overrides.clear()


def test_invalid_signing_code(monkeypatch):
    db=FakeDB(status='ACCEPTED',version=5); lock_fake(monkeypatch,db)
    code=fulfillment.request_signing_code(db,db.actor,db.app_id,5)
    wrong='000000' if code['demo_code']!='000000' else '111111'
    response=fulfillment.sign_application(db,db.actor,db.app_id,5,wrong)
    assert response == {'_bad_code': True}
    assert db.sign_codes['attempts']==1
    assert db.status=='ACCEPTED'


def test_sign_requires_code():
    with pytest.raises(ValidationError):
        SignWithCodeIn(version=5)


def test_sign_code_expires(monkeypatch):
    db=FakeDB(status='ACCEPTED',version=5); lock_fake(monkeypatch,db)
    code=fulfillment.request_signing_code(db,db.actor,db.app_id,5)
    db.sign_codes['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
    with pytest.raises(ApiProblem) as exc:
        fulfillment.sign_application(db,db.actor,db.app_id,5,code['demo_code'])
    assert exc.value.code=='SIGN_CODE_EXPIRED'


def test_sign_code_attempt_limit(monkeypatch):
    db=FakeDB(status='ACCEPTED',version=5); lock_fake(monkeypatch,db)
    code=fulfillment.request_signing_code(db,db.actor,db.app_id,5)
    db.sign_codes['attempts']=5
    with pytest.raises(ApiProblem) as exc:
        fulfillment.sign_application(db,db.actor,db.app_id,5,code['demo_code'])
    assert exc.value.code=='SIGN_CODE_BLOCKED'
