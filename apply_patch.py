#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd()


def change(src: str, old: str, new: str, filename: str) -> str:
    count = src.count(old)
    if count != 1:
        raise ValueError(f'{filename}: ожидаемый фрагмент встречается {count} раз вместо 1; '\
                         'версия проекта отличается. Не меняйте файл вслепую.')
    return src.replace(old, new, 1)


def update(relative: str, original: str) -> str:
    p = relative
    s = original
    if p == 'app/services/workflow.py':
        s = change(s, 'from .applications import _get_raw\n',
                   'from .applications import _get_raw\nfrom .bank_turnover import get_bank_history_metrics\n', p)
        s = change(s, "RULE_VERSION = 'rules-v1'", "RULE_VERSION = 'rules-v2-bank'", p)
        s = change(s, '    input_snapshot = _snapshot(row)\n',
                   "    input_snapshot = _snapshot(row)\n"
                   "    # Freeze bank history as of submission; never reread live operations in scorer.\n"
                   "    input_snapshot['bank_history'] = get_bank_history_metrics(\n"
                   "        conn, row['company_id']\n"
                   "    )\n", p)
    elif p == 'app/scoring/contracts.py':
        s = change(s, 'class ScoringInput(StrictMoney):\n',
                   "class BankHistoryInput(BaseModel):\n"
                   "    status: Literal['COMPLETE', 'INCOMPLETE', 'NO_ACCOUNTS']\n"
                   "    period_months: int = Field(ge=0, default=0)\n"
                   "    account_count: int = Field(ge=0, default=0)\n"
                   "    operations_count: int = Field(ge=0, default=0)\n"
                   "    avg_monthly_sales: Decimal | None = None\n"
                   "    avg_monthly_operating_out: Decimal | None = None\n"
                   "    monthly_sales: list[Decimal] = Field(default_factory=list)\n"
                   "    period_start: str | None = None\n"
                   "    period_end: str | None = None\n"
                   "    months: list[str] = Field(default_factory=list)\n"
                   "    expected_coverage: int = Field(ge=0, default=0)\n"
                   "    covered_account_months: int = Field(ge=0, default=0)\n"
                   "\n"
                   "    @field_validator('avg_monthly_sales', 'avg_monthly_operating_out', 'monthly_sales', mode='before')\n"
                   "    @classmethod\n"
                   "    def reject_float(cls, value):\n"
                   "        if isinstance(value, float) or (isinstance(value, list) and any(isinstance(x, float) for x in value)):\n"
                   "            raise ValueError('Банковские денежные значения не должны быть float')\n"
                   "        return value\n\n\n"
                   "class ScoringInput(StrictMoney):\n", p)
        s = change(s,
                   "    company_registry_flag: Literal['active', 'inactive', 'mismatch', 'unknown']\n",
                   "    company_registry_flag: Literal['active', 'inactive', 'mismatch', 'unknown']\n"
                   "    bank_history: BankHistoryInput | None = None\n", p)
    elif p == 'app/services/scoring_adapter.py':
        s = change(s, 'from ..scoring import score_application\n',
                   'from ..scoring import score_application\nfrom ..scoring.bank_history import calculate_bank_score\n', p)
        s = change(s, "        company_registry_flag=values['FNS'],\n",
                   "        company_registry_flag=values['FNS'],\n"
                   "        bank_history=snapshot.get('bank_history'),\n", p)
        s = change(s, '    factors = {\n',
                   "    bank_factor = calculate_bank_score(inp.bank_history, inp.monthly_revenue)\n"
                   "    factors = {\n", p)
        s = change(s, '        "decision_hint": out.decision_hint,\n',
                   '        "decision_hint": out.decision_hint,\n'
                   '        "bank_history": inp.bank_history.model_dump(mode="json") if inp.bank_history else None,\n'
                   '        "bank_score": bank_factor.score,\n'
                   '        "bank_ratio": str(bank_factor.ratio) if bank_factor.ratio is not None else None,\n'
                   '        "bank_unstable": bank_factor.unstable,\n', p)
    elif p == 'app/scoring/__init__.py':
        s = change(s, 'from app.scoring.rules import evaluate_score_and_risk\n',
                   'from app.scoring.rules import evaluate_score_and_risk\n'
                   'from app.scoring.bank_history import calculate_bank_score, combine_score, risk_for_score\n', p)
        s = change(s, 'RULE_VERSION = "rules-v1"', 'RULE_VERSION = "rules-v2-bank"', p)
        s = change(s, '    reasons.extend(score_reasons)\n',
                   '    reasons.extend(score_reasons)\n'
                   '    bank_factor = calculate_bank_score(data.bank_history, data.monthly_revenue)\n'
                   '    if bank_factor.score is not None:\n'
                   '        score = combine_score(score, bank_factor.score)\n'
                   '        risk_level = risk_for_score(score)\n'
                   '        reasons = [r for r in reasons if r not in ("RISK_MEDIUM", "RISK_HIGH")]\n'
                   '        if risk_level == "MEDIUM":\n'
                   '            reasons.append("RISK_MEDIUM")\n'
                   '        elif risk_level == "HIGH":\n'
                   '            reasons.append("RISK_HIGH")\n'
                   '    reasons.extend(bank_factor.reason_codes)\n', p)
    elif p == 'app/scoring/explain.py':
        s = change(s, 'import httpx\n',
                   'import httpx\nfrom app.scoring.bank_history import calculate_bank_score\n', p)
        s = change(s, '    company_registry_flag: str,\n) -> list[dict[str, Any]]:\n',
                   '    company_registry_flag: str,\n'
                   '    bank_history: dict[str, Any] | None = None,\n'
                   ') -> list[dict[str, Any]]:\n', p)
        s = change(s, '    return [\n        {\n            "factor_code": "CASH_FLOW_MARGIN",',
                   '    factors = [\n        {\n            "factor_code": "CASH_FLOW_MARGIN",', p)
        s = change(s, '    ]\n\nasync def generate_bank_underwriter_summary(',
                   '    ]\n'
                   '    bank = calculate_bank_score(bank_history, revenue)\n'
                   '    if bank.score is not None:\n'
                   '        for factor in factors:\n'
                   '            factor["weight_percent"] = round(factor["weight_percent"] * 0.85, 2)\n'
                   '            factor["weighted_points"] = round(factor["weighted_points"] * 0.85, 2)\n'
                   '        factors.append({\n'
                   '            "factor_code": "BANK_HISTORY", "name": "Поступления по счетам",\n'
                   '            "weight_percent": 15, "raw_score": bank.score,\n'
                   '            "weighted_points": round(0.15 * bank.score, 2),\n'
                   '            "details": bank.details,\n'
                   '        })\n'
                   '    elif bank_history is not None:\n'
                   '        factors.append({\n'
                   '            "factor_code": "BANK_HISTORY_UNAVAILABLE", "name": "История операций (нет оценки)",\n'
                   '            "weight_percent": 0, "raw_score": 70, "weighted_points": 0,\n'
                   '            "details": bank.details,\n'
                   '        })\n'
                   '    return factors\n\nasync def generate_bank_underwriter_summary(', p)
    elif p == 'app/api/v1/bank.py':
        s = change(s, '        company_registry_flag=check_values.get("FNS", "unknown"),\n',
                   '        company_registry_flag=check_values.get("FNS", "unknown"),\n'
                   '        bank_history=snapshot.get("bank_history"),\n', p)
    else:
        raise ValueError(f'Unknown file {p}')
    return s


MODIFY = [
    'app/services/workflow.py',
    'app/scoring/contracts.py',
    'app/services/scoring_adapter.py',
    'app/scoring/__init__.py',
    'app/scoring/explain.py',
    'app/api/v1/bank.py',
]
NEW = [
    'app/services/bank_turnover.py',
    'app/scoring/bank_history.py',
    'db/migrations/20261026_bank_scoring.sql',
    'tests/test_bank_scoring_v2.py',
]


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not (ROOT / 'docker-compose.yml').exists():
        parser.error('Запускайте из корня Hacaton_2026 (там должен быть docker-compose.yml)')
    replacements: dict[str, str] = {}
    try:
        for rel in MODIFY:
            original = (ROOT / rel).read_text(encoding='utf-8')
            replacements[rel] = update(rel, original)
        for rel in NEW:
            if (ROOT / rel).exists():
                raise ValueError(f'{rel} уже существует. Прерываю, чтобы ничего не перезаписать.')
            if not (HERE / rel).exists():
                raise ValueError(f'В архиве отсутствует {rel}')
    except (ValueError, FileNotFoundError) as e:
        print(f'ОСТАНОВЛЕНО: {e}', file=sys.stderr)
        return 1
    print('Проверка совместимости успешна: 6 изменяемых и 4 новых файла.')
    if args.check:
        return 0
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backups = ROOT / f'patch_backups_bank_scoring_{stamp}'
    for rel in MODIFY:
        dst = backups / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    for rel, value in replacements.items():
        (ROOT / rel).write_text(value, encoding='utf-8')
    for rel in NEW:
        dst = ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(HERE / rel, dst)
    print(f'Готово. Резервные копии изменённых файлов: {backups}')
    print('Далее: примените db/migrations/20261026_bank_scoring.sql, тесты и пересборку api.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
