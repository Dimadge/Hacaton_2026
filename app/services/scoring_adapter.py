"""Преобразование сохранённой версии заявки + ФНС/БКИ в ScoringInput.

Здесь НЕТ реализации модели и НЕТ записи результата скоринга в БД.
После получения кода DS можно вызвать score_application(...) и валидировать
результат через ScoringOutput в сервисе BE-07.
"""
from __future__ import annotations

from uuid import UUID
from sqlalchemy import Connection, text
from ..core.errors import ApiProblem
from ..scoring.contracts import ScoringInput


def build_scoring_input(conn: Connection, run_id: UUID) -> ScoringInput:
    row = conn.execute(text('''SELECT input_snapshot,product_snapshot
        FROM alfa.evaluation_runs WHERE id=:run'''), {'run': run_id}).mappings().first()
    if not row:
        raise ApiProblem(404, 'NOT_FOUND', 'Цикл проверки не найден')
    checks = conn.execute(text('''SELECT source,result FROM alfa.verifications
        WHERE run_id=:run'''), {'run': run_id}).mappings().all()
    values = {r['source']: r['result'] for r in checks}
    if set(values) != {'FNS', 'BKI'}:
        raise ApiProblem(409, 'VERIFICATIONS_INCOMPLETE',
                         'Нельзя запускать скоринг до завершения mock-проверок')
    snapshot = row['input_snapshot']
    product = row['product_snapshot']
    return ScoringInput(
        monthly_revenue=snapshot['monthly_revenue'],
        operating_expenses=snapshot['operating_expenses'],
        existing_debt_payments=snapshot['existing_debt_payments'],
        business_age_months=snapshot['business_age_months'],
        requested_amount=snapshot['requested_amount'],
        term_months=snapshot['term_months'],
        demo_rate=product['demo_rate'],
        credit_history_flag=values['BKI'],
        company_registry_flag=values['FNS'],
    )
