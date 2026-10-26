"""Единая детерминированная демонстрационная формула банковского фактора.

Не является промышленной банковской методикой. Не использует float.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True)
class BankScore:
    score: int | None
    ratio: Decimal | None
    unstable: bool
    reason_codes: tuple[str, ...]
    details: str


def _field(data: Any, name: str, default=None):
    if data is None:
        return default
    if isinstance(data, dict):
        return data.get(name, default)
    return getattr(data, name, default)


def calculate_bank_score(history: Any, declared_monthly_revenue: Decimal) -> BankScore:
    status = _field(history, 'status', 'INCOMPLETE')
    if status != 'COMPLETE':
        return BankScore(None, None, False,
                         ('BANK_HISTORY_INCOMPLETE',) if status == 'INCOMPLETE' else (),
                         'Нет подтверждённой истории за три полных месяца')
    sales = Decimal(str(_field(history, 'avg_monthly_sales', '0')))
    revenue = Decimal(str(declared_monthly_revenue))
    if revenue <= 0:
        # Деление на ноль невозможно, нужен ручной разбор противоречия.
        ratio, score = None, 30 if sales > 0 else 50
        codes = ['BANK_TURNOVER_MISMATCH'] if sales > 0 else []
    else:
        ratio = sales / revenue
        if Decimal('0.8') <= ratio <= Decimal('1.2'):
            score = 100
            codes = []
        elif Decimal('0.6') <= ratio <= Decimal('1.5'):
            score = 70
            codes = ['BANK_TURNOVER_MISMATCH']
        else:
            score = 30
            codes = ['BANK_TURNOVER_MISMATCH']
    values = [Decimal(str(x)) for x in _field(history, 'monthly_sales', [])]
    unstable = False
    if len(values) == 3:
        minimum, maximum = min(values), max(values)
        unstable = (minimum == 0 < maximum) or (minimum > 0 and maximum > 2 * minimum)
        if unstable:
            score = max(0, score - 20)
            codes.append('BANK_TURNOVER_UNSTABLE')
    ratio_text = 'не определено' if ratio is None else str(ratio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return BankScore(score, ratio, unstable, tuple(codes),
                     f'Средние поступления SALES={sales} ₽, выручка анкеты={revenue} ₽; отношение={ratio_text}; '
                     f'нестабильность={"да" if unstable else "нет"}')


def combine_score(base_score: int, bank_score: int | None) -> int:
    if bank_score is None:
        return base_score
    blended = (Decimal(base_score) * Decimal('0.85')
               + Decimal(bank_score) * Decimal('0.15'))
    return max(0, min(100, int(blended.quantize(Decimal('1'), rounding=ROUND_HALF_UP))))


def risk_for_score(score: int) -> str:
    return 'LOW' if score >= 75 else 'MEDIUM' if score >= 50 else 'HIGH'
