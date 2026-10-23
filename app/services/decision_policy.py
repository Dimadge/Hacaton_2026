"""BE-07: детерминированная банковская политика для СИНТЕТИЧЕСКИХ данных.

Не заменяет скоринг DS. Из проверок можно сделать вывод об отказе,
запросе документов или необходимости ручного рассмотрения. При благоприятных
проверках без результата DS кредит НЕ одобряется.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyOutcome:
    target_status: str | None
    decision_type: str | None
    reason_codes: tuple[str, ...]
    next_step: str


def decide_preliminary(*, fns: str, bki: str, document_confirmed: bool,
                       score: int | None = None, risk: str | None = None) -> PolicyOutcome:
    """Приоритет правил из MVP: документы -> критические флаги -> review -> скоринг.

    score/risk могут прийти ТОЛЬКО из сохранённого расчёта DS, НЕ из клиента.
    Для LOW пока ожидаем компонент генерации валидных офферов.
    """
    if not document_confirmed:
        return PolicyOutcome('NEED_INFO', 'REQUEST_INFO', ('DOCS_MISSING',), 'ADD_DOCUMENTS')
    if fns == 'inactive':
        return PolicyOutcome('REJECTED', 'REJECT', ('REGISTRY_INACTIVE',), 'FINAL')
    if bki == 'critical':
        return PolicyOutcome('REJECTED', 'REJECT', ('CREDIT_HISTORY_CRITICAL',), 'FINAL')
    if fns != 'active' or bki not in ('good', 'minor_delay'):
        reasons = ('REGISTRY_MISMATCH',) if fns == 'mismatch' else ('UNKNOWN_VERIFICATION',)
        if bki == 'unknown' and 'UNKNOWN_VERIFICATION' not in reasons:
            reasons += ('UNKNOWN_VERIFICATION',)
        return PolicyOutcome('UNDER_REVIEW', 'MANUAL_REVIEW', reasons, 'BANK_REVIEW')
    if bki == 'minor_delay':
        return PolicyOutcome('UNDER_REVIEW', 'MANUAL_REVIEW', ('CREDIT_HISTORY_DELAY',), 'BANK_REVIEW')
    if score is None or risk is None:
        return PolicyOutcome(None, None, (), 'SCORING_PENDING')
    if risk == 'HIGH':
        return PolicyOutcome('REJECTED', 'REJECT', ('RISK_HIGH',), 'FINAL')
    if risk == 'MEDIUM':
        return PolicyOutcome('UNDER_REVIEW', 'MANUAL_REVIEW', ('RISK_MEDIUM',), 'BANK_REVIEW')
    if risk == 'LOW':
        return PolicyOutcome(None, None, (), 'OFFERS_PENDING')
    raise ValueError('Неверная категория риска')
