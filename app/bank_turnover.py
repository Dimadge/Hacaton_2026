"""Снимок проверенных оборотов юридического лица для конкретного evaluation_run.

Не меняем таблицы 003/004. Не используем личные счета физлиц.
Берём последние три *полных* календарных месяца UTC на момент подачи заявки.
Пока история не подтверждена по ВСЕМ счетам / всем месяцам, балл не рассчитывается.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text


def _shift_month(first_day: date, delta: int) -> date:
    month = first_day.year * 12 + first_day.month - 1 + delta
    return date(month // 12, month % 12 + 1, 1)


def get_bank_history_metrics(
    conn: Connection,
    company_id: UUID,
    *,
    as_of: date | None = None,
) -> dict:
    """Возвращает JSON-совместимые строки вместо float/Decimal.

    Данные фильтруются исключительно по company_id из сохранённой заявки.
    Статусы: NO_ACCOUNTS, INCOMPLETE, COMPLETE.
    """
    as_of = as_of or datetime.now(timezone.utc).date()
    period_end = date(as_of.year, as_of.month, 1)
    period_start = _shift_month(period_end, -3)
    months = [_shift_month(period_start, i) for i in range(3)]
    account_count = conn.execute(
        text("SELECT count(*) FROM alfa.bank_accounts WHERE company_id=:company"),
        {'company': company_id},
    ).scalar_one()
    result = {
        'status': 'NO_ACCOUNTS' if account_count == 0 else 'INCOMPLETE',
        'period_start': period_start.isoformat(),
        'period_end': period_end.isoformat(),
        'months': [m.isoformat() for m in months],
        'period_months': 3,
        'account_count': int(account_count),
        'expected_coverage': int(account_count) * 3,
        'covered_account_months': 0,
        'avg_monthly_sales': None,
        'avg_monthly_operating_out': None,
        'monthly_sales': [],
        'operations_count': 0,
    }
    if not account_count:
        return result

    # Coverage = наличие подтверждённой истории, а НЕ число транзакций.
    # Проверяется каждая пара (расчётный счёт компании, календарный месяц).
    covered = conn.execute(text('''
        SELECT count(*) FROM alfa.bank_history_coverage h
        JOIN alfa.bank_accounts a ON a.id=h.account_id
        WHERE a.company_id=:company
          AND h.month >= :start AND h.month < :end
    '''), {'company': company_id, 'start': period_start, 'end': period_end}).scalar_one()
    result['covered_account_months'] = int(covered)
    if int(covered) != result['expected_coverage']:
        return result

    rows = conn.execute(text('''
        SELECT date_trunc('month', o.booked_at AT TIME ZONE 'UTC')::date AS month,
               COALESCE(SUM(o.amount) FILTER (
                   WHERE o.direction='IN' AND o.category='SALES'), 0) AS sales,
               COALESCE(SUM(o.amount) FILTER (
                   WHERE o.direction='OUT' AND o.category='OPERATING'), 0) AS operating_out,
               count(*) AS operations_count
        FROM alfa.bank_operations o
        JOIN alfa.bank_accounts a ON a.id=o.account_id
        WHERE a.company_id=:company
          AND o.booked_at >= :start AND o.booked_at < :end
        GROUP BY 1 ORDER BY 1
    '''), {'company': company_id, 'start': period_start, 'end': period_end}).mappings().all()
    by_month = {r['month']: r for r in rows}
    sales = [Decimal(str(by_month[m]['sales'])) if m in by_month else Decimal('0') for m in months]
    costs = [Decimal(str(by_month[m]['operating_out'])) if m in by_month else Decimal('0') for m in months]
    result.update({
        'status': 'COMPLETE',
        'avg_monthly_sales': str(sum(sales, Decimal('0')) / Decimal('3')),
        'avg_monthly_operating_out': str(sum(costs, Decimal('0')) / Decimal('3')),
        'monthly_sales': [str(v) for v in sales],
        'operations_count': sum(int(r['operations_count']) for r in rows),
    })
    return result
