import os
import json
import httpx
from decimal import Decimal
from typing import Optional, Dict, Any

from app.scoring.contracts import ScoringOutput

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def generate_explanation_prompt(scoring: ScoringOutput, requested_amount: Decimal, term_months: int) -> str:
    reasons_str = ", ".join(scoring.reason_codes) if scoring.reason_codes else "все проверки пройдены"

    offers_str = ""
    for idx, c in enumerate(scoring.candidates, 1):
        offers_str += f"\n- Вариант {idx}: {c.amount:,.0f} ₽ на {c.term_months} мес., платеж {c.monthly_payment:,.2f} ₽/мес."

    prompt = f"""Ты — умный финансовый ассистент Альфа-Банка для предпринимателей.
Твоя задача — вежливо, понятно и без сложного банковского жаргона объяснить предпринимателю решение по кредитной заявке.

ДАННЫЕ РАСЧЕТА (строго опирайся на них, не придумывай свои цифры):
- Запрошено: {requested_amount:,.0f} ₽ на {term_months} мес.
- Кредитный рейтинг бизнеса: {scoring.score} из 100 (уровень риска: {scoring.risk_level})
- Максимально допустимый ежемесячный платеж: {scoring.max_new_monthly_payment:,.2f} ₽
- Вердикт системы: {scoring.decision_hint}
- Причины / факторы: {reasons_str}
- Доступные альтернативы: {offers_str if offers_str else "не сформированы"}

ПРАВИЛА ОТВЕТА:
1. Пиши кратко (не более 3-4 предложений).
2. Если предложен COUNTER_OFFER, объясни, что запрошенный платеж превышает допустимую нагрузку, но банк подготовил удобные варианты с меньшим платежом.
3. Не используй процент одобрения (балл {scoring.score}/100 — это индекс готовности, а не вероятность).
4. Заверши сообщение предложением задать вопрос или проверить сценарий в симуляторе.
"""
    return prompt


def explain_scoring_decision(
        scoring: ScoringOutput,
        requested_amount: Decimal,
        term_months: int
) -> str:
    prompt = generate_explanation_prompt(scoring, requested_amount, term_months)

    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "").strip()
    except Exception:
        pass

    if scoring.decision_hint == "COUNTER_OFFER":
        return (
            f"Ваш предварительный рейтинг кредитной готовности составил {scoring.score}/100. "
            f"Запрошенная сумма создает повышенную нагрузку на текущий денежный поток бизнеса "
            f"(лимит платежа: {scoring.max_new_monthly_payment:,.0f} ₽/мес.). "
            f"Мы рассчитали для вас альтернативные варианты с комфортным ежемесячным платежом."
        )
    elif scoring.decision_hint == "APPROVE":
        return (
            f"Отличные новости! Ваш бизнес показал высокий уровень кредитной готовности ({scoring.score}/100). "
            f"Финансовые потоки полностью покрывают запрашиваемый платеж. Заявка предварительно одобрена."
        )
    elif scoring.decision_hint == "MANUAL_REVIEW":
        return (
            f"Ваш рейтинг готовности составил {scoring.score}/100. "
            f"Заявка направлена на индивидуальное рассмотрение сотруднику банка для уточнения условий."
        )
    else:
        return (
            f"Рейтинг готовности составил {scoring.score}/100. "
            f"К сожалению, текущие показатели бизнеса или кредитной истории пока не позволяют одобрить заявку."
        )