"""BE-06: детерминированная логика поверх fake DB; не заменяет postgres E2E."""
from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.errors import ApiProblem
from app.core.security import Actor, require_client
from app.database import get_connection
from app.main import app
from app.integrations.fns_mock import check_registry
from app.integrations.bki_mock import check_credit_history
from app.scoring.contracts import ScoringInput, ScoringOutput
from app.services import checks
from app.services.scoring_adapter import build_scoring_input


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else ([] if row is None else [row])

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class FakeChecksDB:
    def __init__(self, registry='active', bki='good', status='CHECKING'):
        self.actor = Actor(id=uuid4(), company_id=uuid4(), role='CLIENT')
        self.app_id = uuid4()
        self.run_id = uuid4()
        self.status = status
        self.registry = registry
        self.bki = bki
        self.rows = []
        self.inserts = 0
        self.profile_exists = True
        self.has_run = True
        self.calls = []
        self.snapshot = dict(monthly_revenue='1500000.00', operating_expenses='900000.00',
                             existing_debt_payments='150000.00', business_age_months=36,
                             requested_amount='3000000.00', term_months=36)
        self.product = dict(demo_rate='0.18')

    def execute(self, sql, params=None):
        query = str(sql)
        params = params or {}
        self.calls.append(query)
        if 'FROM alfa.loan_applications' in query:
            if params['app'] != self.app_id or params['company'] != self.actor.company_id:
                return Result()
            return Result({'id':self.app_id, 'status':self.status,
                           'company_id':self.actor.company_id})
        if 'FROM alfa.evaluation_runs' in query and 'submission_version' in query:
            return Result({'id':self.run_id} if self.has_run else None)
        if 'FROM alfa.mock_profiles' in query:
            if not self.profile_exists:
                return Result()
            return Result({'registry_flag':self.registry, 'credit_history_flag':self.bki})
        if 'INSERT INTO alfa.verifications' in query:
            assert params['app'] == self.app_id and params['run'] == self.run_id
            assert params['source'] in ('FNS','BKI')
            self.inserts += 1
            assert params['source'] not in {r['source'] for r in self.rows}
            import json
            assert json.loads(params['payload'])['synthetic'] is True
            self.rows.append({'id':uuid4(), 'run_id':self.run_id,
                              'source':params['source'], 'result':params['result'],
                              'payload':json.loads(params['payload']),
                              'checked_at':'2026-10-23T12:00:00Z'})
            return Result()
        if 'FROM alfa.verifications WHERE run_id' in query:
            return Result(rows=sorted(self.rows, key=lambda r: ('FNS','BKI').index(r['source'])))
        if 'SELECT input_snapshot,product_snapshot' in query:
            return Result({'input_snapshot':self.snapshot,
                           'product_snapshot':self.product})
        if 'SELECT source,result FROM alfa.verifications' in query:
            return Result(rows=[{'source':r['source'],'result':r['result']} for r in self.rows])
        raise AssertionError(f'Unexpected SQL {query}')


@pytest.mark.parametrize('fns,bki,expected_reasons', [
    ('active','good',[]),
    ('active','minor_delay',['CREDIT_HISTORY_DELAY']),
    ('mismatch','good',['REGISTRY_MISMATCH']),
    ('inactive','critical',['CREDIT_HISTORY_CRITICAL','REGISTRY_INACTIVE']),
    ('unknown','unknown',['UNKNOWN_VERIFICATION']),
])
def test_five_deterministic_mock_scenarios(fns,bki,expected_reasons):
    db = FakeChecksDB(fns,bki)
    result = checks.ensure_checks(db, db.actor, db.app_id)
    assert result['application_status'] == 'CHECKING'
    assert result['completed'] is True
    assert [(r['source'],r['result']) for r in result['checks']] == [('FNS',fns),('BKI',bki)]
    assert result['reason_codes'] == expected_reasons
    assert db.inserts == 2
    assert db.status == 'CHECKING'  # BE06 никогда не принимает кредитное решение
    second = checks.ensure_checks(db, db.actor, db.app_id)
    assert db.inserts == 2
    assert second == result


def test_missing_mock_profile_is_unknown_not_good():
    db = FakeChecksDB(); db.profile_exists = False
    result = checks.ensure_checks(db, db.actor, db.app_id)
    assert [r['result'] for r in result['checks']] == ['unknown','unknown']
    assert result['reason_codes'] == ['UNKNOWN_VERIFICATION']
    assert all(r['payload']['mock_profile_present'] is False for r in result['checks'])


def test_partial_saved_history_is_completed_without_overwriting():
    db = FakeChecksDB('active','good')
    db.rows = [{'id':uuid4(),'run_id':db.run_id,'source':'FNS','result':'inactive',
                'payload':{'synthetic':True},'checked_at':'2026-10-23T12:00:00Z'}]
    result = checks.ensure_checks(db, db.actor, db.app_id)
    assert db.inserts == 1
    assert result['checks'][0]['result'] == 'inactive'
    assert result['reason_codes'] == ['REGISTRY_INACTIVE']


def test_no_run_rejects_and_get_draft_yields_empty():
    db = FakeChecksDB(status='DRAFT'); db.has_run = False
    before = checks.get_checks(db, db.actor, db.app_id)
    assert before['completed'] is False and before['checks'] == []
    assert before['evaluation_run_id'] is None
    with pytest.raises(ApiProblem) as err:
        checks.ensure_checks(db, db.actor, db.app_id)
    assert err.value.code == 'NOT_SUBMITTED'


def test_cannot_trigger_checks_after_checking_stage():
    db = FakeChecksDB(status='OFFERED')
    with pytest.raises(ApiProblem) as err:
        checks.ensure_checks(db, db.actor, db.app_id)
    assert err.value.status_code == 409


def test_company_isolation_and_role_guards():
    db = FakeChecksDB()
    outsider = Actor(id=uuid4(), company_id=uuid4(), role='CLIENT')
    with pytest.raises(ApiProblem) as err:
        checks.get_checks(db, outsider, db.app_id)
    assert err.value.status_code == 404
    bank = Actor(id=uuid4(), company_id=None, role='BANK_EMPLOYEE')
    with pytest.raises(ApiProblem) as err:
        checks.ensure_checks(db, bank, db.app_id)
    assert err.value.status_code == 403


def test_fns_bki_normalization():
    assert check_registry(None)[0] == 'unknown'
    assert check_registry('ACTIVE')[0] == 'unknown'
    assert check_credit_history(None)[0] == 'unknown'
    assert check_credit_history('critical')[1] == ('CREDIT_HISTORY_CRITICAL',)


def test_adapter_uses_snapshots_and_decimal_not_float():
    db = FakeChecksDB('active','good')
    with pytest.raises(ApiProblem) as err:
        build_scoring_input(db, db.run_id)
    assert err.value.code == 'VERIFICATIONS_INCOMPLETE'
    checks.ensure_checks(db, db.actor, db.app_id)
    data = build_scoring_input(db, db.run_id)
    assert isinstance(data, ScoringInput)
    assert data.monthly_revenue == Decimal('1500000.00')
    assert type(data.monthly_revenue) is Decimal
    assert data.demo_rate == Decimal('0.18')
    assert data.company_registry_flag == 'active'
    assert data.credit_history_flag == 'good'


def test_rejects_float_money_in_scoring_input():
    with pytest.raises(ValueError):
        ScoringInput(monthly_revenue=1500000.0, operating_expenses='900000.00',
                     existing_debt_payments='150000.00', business_age_months=36,
                     requested_amount='3000000.00', term_months=36, demo_rate='0.18',
                     credit_history_flag='good', company_registry_flag='active')


def test_contract_validation_no_accidental_scoring():
    with pytest.raises(ValueError):
        ScoringOutput(score=110, risk_level='LOW', max_new_monthly_payment='90000.00',
                      decision_hint='APPROVE', candidates=[], reason_codes=[], rule_version='rules-v1')


def test_api_checks_run_and_get(client):
    db = FakeChecksDB('active','minor_delay')
    app.dependency_overrides[require_client] = lambda: db.actor
    app.dependency_overrides[get_connection] = lambda: db
    try:
        post = client.post(f'/api/v1/applications/{db.app_id}/checks/run')
        assert post.status_code == 200, post.text
        assert post.json()['completed'] is True
        assert post.json()['reason_codes'] == ['CREDIT_HISTORY_DELAY']
        get = client.get(f'/api/v1/applications/{db.app_id}/checks')
        assert get.status_code == 200, get.text
        assert get.json()['checks'] == post.json()['checks']
        assert db.inserts == 2
    finally:
        app.dependency_overrides.clear()


def test_api_checks_wrong_client(client):
    db = FakeChecksDB()
    app.dependency_overrides[require_client] = lambda: Actor(id=uuid4(), company_id=uuid4(), role='CLIENT')
    app.dependency_overrides[get_connection] = lambda: db
    try:
        response = client.get(f'/api/v1/applications/{db.app_id}/checks')
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_completed_checks_can_be_replayed_after_bank_evaluation():
    """Идемпотентный повтор submit не должен ломаться, если банк уже обработал заявку."""
    db = FakeChecksDB('active', 'minor_delay')
    first = checks.ensure_checks(db, db.actor, db.app_id)
    assert first['completed'] is True
    db.status = 'UNDER_REVIEW'
    replay = checks.ensure_checks(db, db.actor, db.app_id)
    assert replay['completed'] is True
    assert replay['application_status'] == 'UNDER_REVIEW'
    assert db.inserts == 2
