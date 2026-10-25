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
    """Детерминированный запасной вариант на случай отсутствия LLM."""
    if decision_type == "MANUAL_REVIEW":
        return (
            f"Ваша заявка на сумму {Decimal(str(requested_amount)):,.0f} ₽ передана на индивидуальное рассмотрение "
            f"кредитному эксперту Альфа-Банка.\n\n"
            f"Мы внимательно относимся к особенностям бизнеса каждого клиента: сейчас андеррайтер анализирует "
            f"динамику оборотов вашей компании, чтобы предложить максимально выгодные и безопасные условия.\n\n"
            f"Обычно рассмотрение занимает до 1 рабочего дня. Как только решение будет готово, "
            f"в этом окне появятся персональные предложения."
        )

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
        f"По вашей заявке на {Decimal(str(requested_amount)):,.0f} ₽ проводится проверка. "
        f"Специалист банка свяжется с вами при необходимости уточнения сведений."
    )


def build_prompt(
    decision_type: str,
    requested_amount: Decimal,
    requested_term: int,
    max_payment: Decimal,
    offers: list[dict[str, Any]],
    reason_codes: list[str],
) -> str:
    """Формирует контекст для LLM."""
    offers_desc = ", ".join(
        f"{Decimal(str(o['amount'])):,.0f} ₽ на {o['term_months']} мес. (платеж {Decimal(str(o['monthly_payment'])):,.2f} ₽)"
        for o in offers
    )
    if decision_type == "MANUAL_REVIEW":
        return (
            "Ты — финансовый консультант Альфа-Банка для малого бизнеса. "
            "Заявка клиента отправлена на индивидуальное рассмотрение андеррайтером (ручная проверка). "
            "Напиши теплое и обнадеживающее сообщение для клиента: объясни, что банк не отказывает, "
            "а индивидуально изучает показатели бизнеса для подбора лучших условий. Срок — до 1 рабочего дня. "
            "Объем: 2 коротких абзаца. Тон доброжелательный, без банковского канцелярита."
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
    """Синхронная функция для тестов."""
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
    """Асинхронная генерация объяснения для API клиента."""
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


def calculate_score_breakdown(
    revenue: Decimal,
    expenses: Decimal,
    existing_debt: Decimal,
    business_age_months: int,
    credit_history_flag: str,
    company_registry_flag: str,
) -> list[dict[str, Any]]:
    """Пофакторная раскладка скорингового балла с весами модели."""
    cash_flow = revenue - expenses
    if revenue <= Decimal("0.00") or cash_flow <= Decimal("0.00"):
        x1_raw = 0
        x1_desc = f"Отрицательный или нулевой поток ({cash_flow:,.0f} ₽)"
    else:
        margin = (cash_flow / revenue) * 100
        if margin >= 40:
            x1_raw = 100
            x1_desc = f"Высокая маржинальность потока ({margin:.1f}%)"
        elif margin >= 20:
            x1_raw = 75
            x1_desc = f"Умеренная маржинальность потока ({margin:.1f}%)"
        else:
            x1_raw = 50
            x1_desc = f"Низкая маржинальность потока ({margin:.1f}%)"

    if cash_flow <= Decimal("0.00"):
        x2_raw = 0
        x2_desc = "Критическая нагрузка при отсутствии свободного потока"
    else:
        dti = (existing_debt / cash_flow) * 100
        if existing_debt == Decimal("0.00"):
            x2_raw = 100
            x2_desc = "Отсутствие текущих долговых обязательств"
        elif dti <= 25:
            x2_raw = 80
            x2_desc = f"Низкая нагрузка DTI: {dti:.1f}% от свободного потока"
        elif dti <= 40:
            x2_raw = 60
            x2_desc = f"Умеренная нагрузка DTI: {dti:.1f}% от свободного потока"
        elif dti <= 60:
            x2_raw = 40
            x2_desc = f"Повышенная нагрузка DTI: {dti:.1f}% от свободного потока"
        else:
            x2_raw = 10
            x2_desc = f"Критическая нагрузка DTI: {dti:.1f}% от свободного потока"

    bki_map = {
        "good": (100, "Идеальная кредитная история без просрочек"),
        "minor_delay": (60, "Зафиксированы краткосрочные технические просрочки"),
        "critical": (10, "Критические просрочки / дефолты в истории"),
        "unknown": (50, "Кредитная история отсутствует или не найдена"),
    }
    x3_raw, x3_desc = bki_map.get(credit_history_flag, (50, "Неизвестный статус БКИ"))

    fns_map = {
        "active": (100, "Действующее юридическое лицо / ИП в ЕГРЮЛ/ЕГРИП"),
        "mismatch": (50, "Расхождение реквизитов организации"),
        "inactive": (0, "Организация ликвидирована или недействительна"),
        "unknown": (50, "Статус не определен"),
    }
    x4_raw, x4_desc = fns_map.get(company_registry_flag, (50, "Неизвестный статус ФНС"))

    x5_raw = min(100, int((business_age_months / 60) * 100))
    x5_desc = f"Срок ведения деятельности: {business_age_months} мес. (макс. оценка от 60 мес.)"

    return [
        {
            "factor_code": "CASH_FLOW_MARGIN",
            "name": "Операционная маржинальность",
            "weight_percent": 30,
            "raw_score": x1_raw,
            "weighted_points": round(0.30 * x1_raw, 2),
            "details": x1_desc,
        },
        {
            "factor_code": "DEBT_BURDEN_DTI",
            "name": "Текущая долговая нагрузка",
            "weight_percent": 25,
            "raw_score": x2_raw,
            "weighted_points": round(0.25 * x2_raw, 2),
            "details": x2_desc,
        },
        {
            "factor_code": "BKI_HISTORY",
            "name": "Дисциплина по данным БКИ",
            "weight_percent": 20,
            "raw_score": x3_raw,
            "weighted_points": round(0.20 * x3_raw, 2),
            "details": x3_desc,
        },
        {
            "factor_code": "FNS_REGISTRY",
            "name": "Надежность по данным ФНС",
            "weight_percent": 15,
            "raw_score": x4_raw,
            "weighted_points": round(0.15 * x4_raw, 2),
            "details": x4_desc,
        },
        {
            "factor_code": "BUSINESS_AGE",
            "name": "Зрелость компании",
            "weight_percent": 10,
            "raw_score": x5_raw,
            "weighted_points": round(0.10 * x5_raw, 2),
            "details": x5_desc,
        },
    ]


async def generate_bank_underwriter_summary(
    score: int,
    risk_level: str,
    decision_type: str,
    reasons: list[str],
    breakdown: list[dict[str, Any]],
) -> str:
    """Генерация аналитического резюме для андеррайтера через LLM / шаблон."""
    drivers_positive = [f["name"] for f in breakdown if f["raw_score"] >= 75]
    drivers_negative = [f["name"] + f" ({f['details']})" for f in breakdown if f["raw_score"] < 70]

    pos_str = ", ".join(drivers_positive) if drivers_positive else "явных драйверов нет"
    neg_str = "; ".join(drivers_negative) if drivers_negative else "критических факторов не выявлено"

    prompt = (
        "Ты — старший кредитный андеррайтер Альфа-Банка. "
        "Сформируй краткое, структурированное заключение для сотрудника банка по скорингу заявки.\n\n"
        f"Итоговый скоринг: {score}/100 (Категория риска: {risk_level})\n"
        f"Рекомендованное решение: {decision_type}\n"
        f"Коды риск-факторов: {', '.join(reasons) if reasons else 'нет'}\n"
        f"Сильные стороны заемщика: {pos_str}\n"
        f"Факторы давления на скоринг: {neg_str}\n\n"
        "Формат заключения (строго 3 пункта):\n"
        "1. Оценка профиля риска: общая характеристика надежности.\n"
        "2. Ключевые риск-триггеры: что привело к снижению балла.\n"
        "3. Рекомендация андеррайтеру: согласовать, отказать или какие документы запросить при ручной проверке."
    )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=1.0)) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
            )
            if resp.status_code == 200:
                text_out = resp.json().get("response", "").strip()
                if text_out:
                    return text_out
    except Exception:
        pass

    return (
        f"ЗАКЛЮЧЕНИЕ СКОРИНГОВОЙ МОДЕЛИ (Оценка: {score}/100, Риск: {risk_level}):\n"
        f"• Сильные стороны: {pos_str}.\n"
        f"• Факторы риска: {neg_str}.\n"
        f"• Рекомендация: "
        + (
            "Одобрение рекомендовано. Параметры заявки в пределах риск-аппетита банка."
            if risk_level == "LOW" and decision_type in ("APPROVE", "COUNTER_OFFER")
            else "Требуется ручная проверка. Запросите оборотно-сальдовую ведомость (ОСВ) за 6 месяцев и справку об отсутствии картотеки №2."
            if risk_level == "MEDIUM" or decision_type == "MANUAL_REVIEW"
            else "Отказ. Уровень риска превышает допустимый лимит."
        )
    )