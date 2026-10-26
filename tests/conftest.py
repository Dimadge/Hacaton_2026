"""Общие fixtures API и изолированные настройки демонстрационных unit-тестов."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as http:
        yield http


@pytest.fixture(autouse=True)
def legacy_workflow_bank_history_stub(monkeypatch, request):
    """Старые тесты submit/resubmit используют SQL-заглушки без таблиц счетов.

    Подменяем только источник банковской истории для этих unit-тестов.
    Реальный bank_turnover и отдельные тесты скоринга остаются без изменений.
    """
    if request.node.path.name not in {'test_submit.py', 'test_resubmit.py'}:
        return

    from app.services import workflow

    original_snapshot = workflow._snapshot

    def no_accounts():
        return {'status': 'NO_ACCOUNTS'}

    def snapshot_with_bank_history(row):
        snapshot = original_snapshot(row)
        snapshot['bank_history'] = no_accounts()
        return snapshot

    monkeypatch.setattr(workflow, '_snapshot', snapshot_with_bank_history)
    monkeypatch.setattr(
        workflow,
        'get_bank_history_metrics',
        lambda conn, company_id: no_accounts(),
    )


@pytest.fixture(autouse=True)
def signing_demo_mode_for_tests(monkeypatch, request):
    """Разрешить тестовые OTP только в тестах BE-08, не в запущенном API."""
    if request.node.path.name == 'test_be08.py':
        monkeypatch.setenv('DEMO_SIGNING_CODE_VISIBLE', 'true')
