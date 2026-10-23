"""Локальная имитация реестра ФНС: не делает внешних запросов.

Единственный источник данных — сохранённый в БД флаг demo-company.
Не вычисляем активность компании по ИНН, названию или дате регистрации.
"""
from typing import Literal

FNSFlag = Literal['active', 'inactive', 'mismatch', 'unknown']
FNS_REASON = {
    'active': (),
    'inactive': ('REGISTRY_INACTIVE',),
    'mismatch': ('REGISTRY_MISMATCH',),
    'unknown': ('UNKNOWN_VERIFICATION',),
}


def check_registry(flag: str | None) -> tuple[FNSFlag, tuple[str, ...]]:
    result = flag if flag in FNS_REASON else 'unknown'
    return result, FNS_REASON[result]
