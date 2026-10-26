from datetime import date
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

from app.scoring.bank_history import calculate_bank_score, combine_score, risk_for_score
from app.services.bank_turnover import _shift_month, get_bank_history_metrics
from app.scoring.contracts import BankHistoryInput, ScoringInput
from app.scoring import score_application


def complete(sales=('1500000', '1500000', '1500000')):
    return {
        'status': 'COMPLETE', 'period_months': 3, 'account_count': 1,
        'operations_count': 100,
        'avg_monthly_sales': str(sum(map(Decimal, sales))/3),
        'avg_monthly_operating_out': '800000',
        'monthly_sales': list(sales),
    }


def _input(history):
    return ScoringInput(
        monthly_revenue='1500000', operating_expenses='900000', existing_debt_payments='100000',
        business_age_months=48, requested_amount='1000000', term_months=24,
        demo_rate='0.20', credit_history_flag='good', company_registry_flag='active',
        bank_history=history,
    )


def test_bank_factor_changes_final_score():
    good = score_application(_input(complete()))
    weak = score_application(_input(complete(('500000', '500000', '500000'))))
    assert good.score > weak.score
    assert weak.risk_level == risk_for_score(weak.score)
    assert 'BANK_TURNOVER_MISMATCH' in weak.reason_codes


def test_missing_coverage_keeps_old_scoring():
    baseline = score_application(_input(None))
    incomplete = score_application(_input({'status': 'INCOMPLETE'}))
    assert baseline.score == incomplete.score
    assert baseline.risk_level == incomplete.risk_level
    assert 'BANK_HISTORY_INCOMPLETE' in incomplete.reason_codes


def test_unstable_flow_penalized():
    stable = calculate_bank_score(complete(), Decimal('1500000'))
    unstable = calculate_bank_score(complete(('0', '2250000', '2250000')), Decimal('1500000'))
    assert unstable.score < stable.score
    assert 'BANK_TURNOVER_UNSTABLE' in unstable.reason_codes


def test_decimal_no_float_and_no_double_blend():
    assert combine_score(80, None) == 80
    assert combine_score(80, 30) == 73
    try:
        BankHistoryInput(status='COMPLETE', avg_monthly_sales=1.5)
    except ValueError:
        pass
    else:
        raise AssertionError('float must be rejected')


def test_month_boundaries():
    assert _shift_month(date(2026, 1, 1), -3) == date(2025, 10, 1)


def test_no_accounts_never_reads_transactions():
    conn = Mock()
    conn.execute.return_value.scalar_one.return_value = 0
    data = get_bank_history_metrics(conn, uuid4(), as_of=date(2026, 10, 26))
    assert data['status'] == 'NO_ACCOUNTS'
    assert conn.execute.call_count == 1


def test_incomplete_coverage_never_reads_transactions():
    conn = Mock()
    conn.execute.side_effect = [Mock(scalar_one=Mock(return_value=1)),
                                Mock(scalar_one=Mock(return_value=2))]
    data = get_bank_history_metrics(conn, uuid4(), as_of=date(2026, 10, 26))
    assert data['status'] == 'INCOMPLETE'
    assert data['expected_coverage'] == 3
    assert conn.execute.call_count == 2
