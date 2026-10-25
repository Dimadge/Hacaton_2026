"""BE-07: тесты чистой политики и банковского API (без запуска PostgreSQL).

Дополнительно необходимо ручное E2E в Swagger + PostgreSQL на MacBook.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.main import app
from app.core.errors import ApiProblem
from app.core.security import Actor, require_bank_employee, require_client
from app.database import get_connection
from app.schemas.decision import BankDecisionIn
from app.services.decision_policy import decide_preliminary
from app.services import decisions


@pytest.mark.parametrize('fns,bki,documented,risk,target,kind,reason,next_step', [
    ('active','good',False,None,'NEED_INFO','REQUEST_INFO','DOCS_MISSING','ADD_DOCUMENTS'),
    ('inactive','good',True,None,'REJECTED','REJECT','REGISTRY_INACTIVE','FINAL'),
    ('active','critical',True,None,'REJECTED','REJECT','CREDIT_HISTORY_CRITICAL','FINAL'),
    ('mismatch','good',True,None,'UNDER_REVIEW','MANUAL_REVIEW','REGISTRY_MISMATCH','BANK_REVIEW'),
    ('active','minor_delay',True,None,'UNDER_REVIEW','MANUAL_REVIEW','CREDIT_HISTORY_DELAY','BANK_REVIEW'),
    ('unknown','good',True,None,'UNDER_REVIEW','MANUAL_REVIEW','UNKNOWN_VERIFICATION','BANK_REVIEW'),
    ('active','unknown',True,None,'UNDER_REVIEW','MANUAL_REVIEW','UNKNOWN_VERIFICATION','BANK_REVIEW'),
    ('active','good',True,None,None,None,None,'SCORING_PENDING'),
    ('active','good',True,'HIGH','REJECTED','REJECT','RISK_HIGH','FINAL'),
    ('active','good',True,'MEDIUM','UNDER_REVIEW','MANUAL_REVIEW','RISK_MEDIUM','BANK_REVIEW'),
    ('active','good',True,'LOW',None,None,None,'OFFERS_PENDING'),
])
def test_policy(fns,bki,documented,risk,target,kind,reason,next_step):
    outcome = decide_preliminary(fns=fns,bki=bki,document_confirmed=documented,
                                 score=85 if risk else None, risk=risk)
    assert (outcome.target_status,outcome.decision_type,outcome.next_step) == (target,kind,next_step)
    if reason:
        assert reason in outcome.reason_codes
    else:
        assert outcome.reason_codes == ()


def test_critical_overrides_manual():
    out = decide_preliminary(fns='mismatch',bki='critical',document_confirmed=True)
    assert out.target_status == 'REJECTED'
    assert out.reason_codes == ('CREDIT_HISTORY_CRITICAL',)


def test_valid_offer_annuity_and_zero_rate():
    assert decisions.annuity(Decimal('12000'),12,Decimal('0')) == Decimal('1000.00')
    assert decisions.annuity(Decimal('3000000'),48,Decimal('0.18')) < Decimal('90000')
    assert decisions.annuity(Decimal('3000000'),36,Decimal('0.18')) > Decimal('90000')
    with pytest.raises(ValueError):
        decisions.annuity(Decimal('-1'),12,Decimal('0.18'))


def test_bank_decision_contract():
    BankDecisionIn(version=3,action='REQUEST_INFO',reason_codes=['DOCS_MISSING'])
    BankDecisionIn(version=4,action='APPROVE',offers=[{'amount':'1000000.00','term_months':36}])
    for payload in [
        {'version':3, 'action':'APPROVE'},
        {'version':3, 'action':'REQUEST_INFO'},
        {'version':3, 'action':'REJECT', 'reason_codes':['RISK_HIGH','RISK_HIGH']},
        {'version':3, 'action':'REJECT', 'reason_codes':['RISK_HIGH'], 'offers':[{'amount':'1000000','term_months':36}]},
        {'version':3, 'action':'APPROVE', 'offers':[{'amount':1000000.0,'term_months':36}]},
    ]:
        with pytest.raises(ValidationError):
            BankDecisionIn.model_validate(payload)


class RowResult:
    def __init__(self, one=None, many=None, scalar=None):
        self.one, self.many, self.scalar = one, many, scalar
    def mappings(self): return self
    def first(self): return self.one
    def all(self): return self.many if self.many is not None else []
    def scalar_one(self): return self.scalar
    def scalar_one_or_none(self): return self.scalar
    def scalars(self): return self


class FakeBankDB:
    """Минимальная stateful SQL-модель для проверки поведения сервиса."""
    def __init__(self,fns='active',bki='good',documented=True,score=None,risk=None,status='CHECKING'):
        self.app_id, self.run_id, self.company_id = uuid4(),uuid4(),uuid4()
        self.actor = Actor(id=uuid4(),role='BANK_EMPLOYEE',company_id=None)
        self.status, self.version = status, 3
        self.fns, self.bki, self.documented = fns,bki,documented
        self.score, self.risk = score,risk
        self.collateral = []
        self.decisions = []
        self.reasons = []
        self.offers = []
        self.updates = 0

    def execute(self,stmt,params=None):
        sql = str(stmt)
        params = params or {}
        if 'FROM alfa.loan_applications a' in sql and 'WHERE a.id=:app' in sql:
            if params['app'] != self.app_id: return RowResult()
            return RowResult(one={'id':self.app_id,'status':self.status,'version':self.version,
                'company_id':self.company_id,'company_name':'Демо-компания',
                'requested_amount':Decimal('3000000'),'term_months':36,
                'created_at':datetime.now(timezone.utc),'product_code':'INVESTMENT',
                'document_confirmed':self.documented})
        if 'FROM alfa.evaluation_runs WHERE application_id' in sql:
            return RowResult(one={'id':self.run_id, 'input_snapshot':{'document_confirmed':self.documented},
               'product_snapshot':{'min_amount':'500000','max_amount':'5000000',
                    'min_term':12,'max_term':60,'demo_rate':'0.18'}, 'rule_version':'rules-v1'})
        if 'FROM alfa.verifications' in sql:
            return RowResult(many=[{'source':'FNS','result':self.fns},{'source':'BKI','result':self.bki}])
        if 'FROM alfa.application_collateral' in sql:
            return RowResult(many=self.collateral)
        if 'FROM alfa.scoring_results' in sql:
            return RowResult(one=({'score':self.score,'risk':self.risk,
                                   'max_new_payment':Decimal('90000')} if self.score is not None else None))
        if 'SELECT COALESCE(MAX(sequence_no)' in sql: return RowResult(scalar=len(self.decisions)+1)
        if 'INSERT INTO alfa.credit_decisions' in sql:
            ident=uuid4(); self.decisions.append((ident,params)); return RowResult(scalar=ident)
        if 'FROM alfa.reason_codes' in sql: return RowResult(scalar=1 if params['code'] in
            {'DOCS_MISSING','REGISTRY_INACTIVE','CREDIT_HISTORY_CRITICAL','CREDIT_HISTORY_DELAY',
             'REGISTRY_MISMATCH','UNKNOWN_VERIFICATION','RISK_HIGH','RISK_MEDIUM', 'COLLATERAL_LIMIT'} else None)
        if 'INSERT INTO alfa.decision_reasons' in sql:
            self.reasons.append(params['code']); return RowResult()
        if "set_config('app.actor_id'" in sql: return RowResult()
        if 'UPDATE alfa.loan_applications' in sql:
            assert self.status==params['previous'] and self.version==params['version']
            self.status=params['target']; self.version+=1; self.updates+=1
            return RowResult(one={'version':self.version})
        if 'INSERT INTO alfa.credit_offers' in sql:
            self.offers.append(params); return RowResult()
        if 'FROM alfa.loan_applications a' in sql and 'WHERE a.status' in sql:
            return RowResult(many=[])
        raise AssertionError('Unexpected SQL: '+sql)


@pytest.mark.parametrize('fns,bki,documented,expected',[
    ('active','good',True,'CHECKING'),('active','good',False,'NEED_INFO'),
    ('active','critical',True,'REJECTED'),('active','minor_delay',True,'UNDER_REVIEW'),
])
def test_bank_evaluate_db(fns,bki,documented,expected):
    db=FakeBankDB(fns,bki,documented)
    result=decisions.bank_evaluate(db,db.actor,db.app_id)
    assert result['status']==expected
    if expected=='CHECKING':
        assert result['next_step']=='SCORING_PENDING'
        assert db.updates==0 and not db.decisions
    else:
        assert db.updates==1 and len(db.decisions)==1
        assert db.status==expected and result['version']==4
        with pytest.raises(ApiProblem) as conflict:
            decisions.bank_evaluate(db,db.actor,db.app_id)
        assert conflict.value.status_code==409


def test_bank_manual_request_info_reject_and_stale_version():
    for action,reasons,target in [('REQUEST_INFO',['DOCS_MISSING'],'NEED_INFO'),
                                  ('REJECT',['CREDIT_HISTORY_DELAY'],'REJECTED')]:
        db=FakeBankDB('active','minor_delay',status='UNDER_REVIEW')
        with pytest.raises(ApiProblem) as err:
            decisions.manual_decision(db,db.actor,db.app_id,
                BankDecisionIn(version=2,action=action,reason_codes=reasons))
        assert err.value.code=='VERSION_CONFLICT'
        result=decisions.manual_decision(db,db.actor,db.app_id,
            BankDecisionIn(version=3,action=action,reason_codes=reasons))
        assert result['status']==target and db.updates==1 and db.reasons==reasons


def test_bank_cannot_approve_without_ds():
    db=FakeBankDB('active','minor_delay',status='UNDER_REVIEW')
    data=BankDecisionIn(version=3,action='APPROVE',offers=[{'amount':'3000000','term_months':48}])
    with pytest.raises(ApiProblem) as exc:
        decisions.manual_decision(db,db.actor,db.app_id,data)
    assert exc.value.code=='SCORING_PENDING'
    assert db.updates==0 and db.decisions==[]


def test_bank_offer_guard_after_ds_result():
    db=FakeBankDB('active','minor_delay',score=65,risk='MEDIUM',status='UNDER_REVIEW')
    data=BankDecisionIn(version=3,action='APPROVE',offers=[{'amount':'3000000','term_months':48}])
    out=decisions.manual_decision(db,db.actor,db.app_id,data)
    assert out['status']=='OFFERED'
    assert db.offers[0]['payment'] <= Decimal('90000')
    assert len(db.decisions)==1
    with pytest.raises(ApiProblem):
        decisions.manual_decision(db,db.actor,db.app_id,data)


def test_bank_deny_invalid_offer():
    db=FakeBankDB(score=65,risk='MEDIUM',status='UNDER_REVIEW')
    data=BankDecisionIn(version=3,action='APPROVE',offers=[{'amount':'3000000','term_months':36}])
    with pytest.raises(ApiProblem) as err:
        decisions.manual_decision(db,db.actor,db.app_id,data)
    assert err.value.code=='PAYMENT_OVER_LIMIT'
    assert not db.decisions


def test_bank_routes_require_bank_role(client):
    # Dependency injection only on DB; role guard still verifies actual JWT.
    app.dependency_overrides[get_connection]=lambda: FakeBankDB()
    try:
        for method,path in [('get','/api/v1/bank/applications'),
                            ('post',f'/api/v1/bank/applications/{uuid4()}/evaluate')]:
            response=getattr(client,method)(path)
            assert response.status_code==401
    finally:
        app.dependency_overrides.clear()


def test_bank_routes_with_bank_actor(client):
    db=FakeBankDB('active','critical')
    app.dependency_overrides[require_bank_employee]=lambda: db.actor
    app.dependency_overrides[get_connection]=lambda: db
    try:
        result=client.post(f'/api/v1/bank/applications/{db.app_id}/evaluate')
        assert result.status_code==200,result.text
        assert result.json()['status']=='REJECTED'
    finally:
        app.dependency_overrides.clear()


def test_bank_client_role_is_forbidden(client):
    from app.core.security import get_current_user
    user = Actor(id=uuid4(),company_id=uuid4(),role='CLIENT')
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_connection] = lambda: FakeBankDB()
    try:
        response = client.get('/api/v1/bank/applications')
        assert response.status_code == 403
        assert response.json()['code'] == 'FORBIDDEN'
    finally:
        app.dependency_overrides.clear()


def test_bank_queue_response_is_list(client):
    db = FakeBankDB()
    app.dependency_overrides[require_bank_employee] = lambda: db.actor
    app.dependency_overrides[get_connection] = lambda: db
    try:
        resp=client.get('/api/v1/bank/applications')
        assert resp.status_code == 200,resp.text
        assert resp.json()==[]
    finally:
        app.dependency_overrides.clear()


def test_bank_action_requires_status_under_review():
    db=FakeBankDB(status='CHECKING')
    with pytest.raises(ApiProblem) as err:
        decisions.manual_decision(db,db.actor,db.app_id,
            BankDecisionIn(version=3,action='REJECT',reason_codes=['RISK_HIGH']))
    assert err.value.code == 'INVALID_STATE_TRANSITION'


def test_collateral_rejects_excess_amount():
    db = FakeBankDB(
        score=65,
        risk="MEDIUM",
        status="UNDER_REVIEW",
    )

    db.collateral = [{
        "status": "ACCEPTED",
        "assessed_value": Decimal("2000000.00"),
        "has_encumbrance": False,
    }]

    offer = BankDecisionIn(
        version=3,
        action="APPROVE",
        offers=[{
            "amount": "1500000.00",
            "term_months": 48,
        }],
    )

    with pytest.raises(ApiProblem) as exc:
        decisions.manual_decision(
            db, db.actor, db.app_id, offer
        )

    assert exc.value.code == "COLLATERAL_LIMIT"
    assert db.offers == []


def test_collateral_accepts_amount_within_limit():
    db = FakeBankDB(
        score=65,
        risk="MEDIUM",
        status="UNDER_REVIEW",
    )

    db.collateral = [{
        "status": "ACCEPTED",
        "assessed_value": Decimal("2000000.00"),
        "has_encumbrance": False,
    }]

    offer = BankDecisionIn(
        version=3,
        action="APPROVE",
        offers=[{
            "amount": "1000000.00",
            "term_months": 48,
        }],
    )

    result = decisions.manual_decision(
        db, db.actor, db.app_id, offer
    )

    assert result["status"] == "OFFERED"
    assert len(db.offers) == 1


def test_unreviewed_collateral_blocks_approval():
    db = FakeBankDB(
        score=65,
        risk="MEDIUM",
        status="UNDER_REVIEW",
    )

    db.collateral = [{
        "status": "DECLARED",
        "assessed_value": None,
        "has_encumbrance": False,
    }]

    offer = BankDecisionIn(
        version=3,
        action="APPROVE",
        offers=[{
            "amount": "1000000.00",
            "term_months": 48,
        }],
    )

    with pytest.raises(ApiProblem) as exc:
        decisions.manual_decision(
            db, db.actor, db.app_id, offer
        )

    assert exc.value.code == "COLLATERAL_PENDING"
    assert db.offers == []


def test_auto_offer_blocked_by_collateral(monkeypatch):
    from types import SimpleNamespace
    import app.scoring
    import app.services.scoring_adapter

    db = FakeBankDB(score=85, risk="LOW")

    db.collateral = [{
        "status": "ACCEPTED",
        "assessed_value": Decimal("2000000.00"),
        "has_encumbrance": False,
    }]

    candidate = SimpleNamespace(
        amount=Decimal("2000000.00"),
        term_months=48,
        rate=Decimal("0.18"),
        monthly_payment=Decimal("50000.00"),
    )

    output = SimpleNamespace(
        candidates=[candidate],
        decision_hint="APPROVE",
        reason_codes=[],
    )

    monkeypatch.setattr(
        app.scoring,
        "score_application",
        lambda inp: output,
    )

    monkeypatch.setattr(
        app.services.scoring_adapter,
        "build_scoring_input",
        lambda conn, run: None,
    )

    result = decisions.bank_evaluate(
        db, db.actor, db.app_id
    )

    assert result["status"] == "UNDER_REVIEW"
    assert result["reason_codes"] == ["COLLATERAL_LIMIT"]
    assert db.offers == []
