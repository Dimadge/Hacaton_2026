"""Модуль объяснения кредитных решений и альтернатив с помощью LLM (Ollama).

Поддерживает работу с локальной моделью Ollama и автоматический откат к шаблону
при недоступности нейросети или превышении таймаута.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any
import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")


def build_fallback_explanation(
    decision_type: str,
    requested_amount: Decimal,
    requested_term: int,
    max_payment: Decimal,
    offers: list[dict[str, Any]],
    reason_codes: list[str],
) -> str:
    if decision_type == "COUNTER_OFFER":
        offers_lines = []
        for i, o in enumerate(offers, 1):
            amt = Decimal(str(o["amount"]))
            term = o["term_months"]
            pmt = Decimal(str(o["monthly_payment"]))
            offers_lines.append(f"  • Вариант {i}: {amt:,.0f} ₽ на {term} мес. с платежом {pmt:,.2f} ₽/мес.")
        offers_text = "\n".join(offers_lines) if offers_lines else "  • Доступны индивидуальные условия."

        return (
            f"Мы внимательно изучили вашу заявку на {Decimal(str(requested_amount)):,.0f} ₽ (срок {requested_term} мес.).\n\n"
            f"Запрошенный платёж превышает комфортный лимит долговой нагрузки для вашего бизнеса "
            f"(максимально допустимый платёж — {Decimal(str(max_payment)):,.2f} ₽/мес.).\n\n"
            f"Чтобы не создавать кассовых разрывов, банк рассчитал для вас альтернативные варианты:\n"
            f"{offers_text}\n\n"
            f"Вы можете выбрать подходящий вариант прямо сейчас в личном кабинете."
        )

    if decision_type == "APPROVE":
        return (
            f"Поздравляем! Ваша заявка на сумму {Decimal(str(requested_amount)):,.0f} ₽ одобрена на запрошенных условиях. "
            f"Договор готов к подписанию."
        )

    return (
        f"По вашей заявке на {Decimal(str(requested_amount)):,.0f} ₽ требуется дополнительная информация "
        f"или ручная проверка параметров бизнеса."
    )


def build_prompt(
    decision_type: str,
    requested_amount: Decimal,
    requested_term: int,
    max_payment: Decimal,
    offers: list[dict[str, Any]],
    reason_codes: list[str],
) -> str:
    offers_desc = ", ".join(
        f"{Decimal(str(o['amount'])):,.0f} ₽ на {o['term_months']} мес. (платеж {Decimal(str(o['monthly_payment'])):,.2f} ₽)"
        for o in offers
    )
    return (
        "Ты — финансовый консультант Альфа-Банка для малого бизнеса. "
        "Твоя задача: вежливо, просто и без банковского канцелярита объяснить клиенту "
        "причину изменения условий по кредиту и презентовать подобранные банком альтернативы.\n\n"
        "Параметры заявки:\n"
        f"- Запрошено: {Decimal(str(requested_amount)):,.0f} руб. на {requested_term} мес.\n"
        f"- Максимально безопасный ежемесячный платеж: {Decimal(str(max_payment)):,.2f} руб.\n"
        f"- Причины корректировки: {', '.join(reason_codes)}\n"
        f"- Встречные предложения банка: {offers_desc}\n\n"
        "Требования к ответу:\n"
        "1. Не используй формулировки 'Вам отказано'. Покажи заботу об устойчивости компании.\n"
        "2. Перечисли предложенные варианты и укажи, как они помогают снизить ежемесячный платеж.\n"
        "3. Объем ответа: 2-3 коротких абзаца. Тон доброжелательный и конструктивный."
    )


def explain_scoring_decision(
    result: Any,
    requested_amount: Decimal,
    term_months: int,
) -> str:
    decision_type = getattr(result, "decision_hint", "COUNTER_OFFER")
    max_payment = getattr(result, "max_new_monthly_payment", Decimal("0"))
    reason_codes = list(getattr(result, "reason_codes", []))
    raw_candidates = getattr(result, "candidates", [])

    offers = []
    for c in raw_candidates:
        if isinstance(c, dict):
            offers.append({
                "amount": c.get("amount", Decimal("0")),
                "term_months": c.get("term_months", 0),
                "monthly_payment": c.get("monthly_payment", Decimal("0")),
            })
        else:
            offers.append({
                "amount": getattr(c, "amount", Decimal("0")),
                "term_months": getattr(c, "term_months", 0),
                "monthly_payment": getattr(c, "monthly_payment", Decimal("0")),
            })

    prompt = build_prompt(
        decision_type,
        Decimal(str(requested_amount)),
        int(term_months),
        Decimal(str(max_payment)),
        offers,
        reason_codes,
    )

    try:
        with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
            resp = client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
            )
            if resp.status_code == 200:
                out_text = resp.json().get("response", "").strip()
                if out_text:
                    return out_text
    except Exception:
        pass

    return build_fallback_explanation(
        decision_type,
        Decimal(str(requested_amount)),
        int(term_months),
        Decimal(str(max_payment)),
        offers,
        reason_codes,
    )


async def generate_explanation(
    decision_type: str,
    requested_amount: Decimal,
    requested_term: int,
    max_payment: Decimal,
    offers: list[dict[str, Any]],
    reason_codes: list[str],
) -> str:
    prompt = build_prompt(
        decision_type,
        Decimal(str(requested_amount)),
        int(requested_term),
        Decimal(str(max_payment)),
        offers,
        reason_codes,
    )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
            )
            if resp.status_code == 200:
                out_text = resp.json().get("response", "").strip()
                if out_text:
                    return out_text
    except Exception:
        pass

    return build_fallback_explanation(
        decision_type,
        Decimal(str(requested_amount)),
        int(requested_term),
        Decimal(str(max_payment)),
        offers,
        reason_codes,
    )