"""Локальная имитация БКИ: фиксированные синтетические флаги, без внешних API."""
from typing import Literal

BKIFlag = Literal['good', 'minor_delay', 'critical', 'unknown']
BKI_REASON = {
    'good': (),
    'minor_delay': ('CREDIT_HISTORY_DELAY',),
    'critical': ('CREDIT_HISTORY_CRITICAL',),
    'unknown': ('UNKNOWN_VERIFICATION',),
}


def check_credit_history(flag: str | None) -> tuple[BKIFlag, tuple[str, ...]]:
    result = flag if flag in BKI_REASON else 'unknown'
    return result, BKI_REASON[result]
