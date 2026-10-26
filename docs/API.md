# API — обзор конечных точек

Интерактивная спецификация: **`http://localhost:8000/docs`**, машинная OpenAPI — **`http://localhost:8000/openapi.json`**. Базовый префикс API: `/api/v1`.

**Авторизация:** `POST /auth/login` возвращает JWT; защищённые маршруты принимают `Authorization: Bearer <token>`. Роли: `CLIENT` и `BANK_EMPLOYEE`. Формат денег в запросах — строки, например `"1500000.00"`; `version` проверяется сервером. Для отправки доступен `Idempotency-Key`.

## Общие и авторизация

| Метод | Маршрут | Роль | Назначение |
| --- | --- | --- | --- |
| GET | `/health` | публичный | Готовность HTTP-процесса (не проверяет БД) |
| GET | `/ready` | публичный | Подключение к PostgreSQL |
| POST | `/api/v1/auth/register` | публичный | Регистрация компании и пользователя |
| POST | `/api/v1/auth/login` | публичный | JWT-токен |
| GET | `/api/v1/products` | публичный | Два кредитных продукта |
| GET | `/api/v1/me/company` | CLIENT | Профиль собственной компании |

## Заявки клиента (`/api/v1/applications`)

| Метод | Окончание | Назначение |
| --- | --- | --- |
| GET | `/` | Мои заявки |
| POST | `/` | Новый черновик с финансовой анкетой |
| GET | `/{id}` | Просмотр своей заявки |
| PATCH | `/{id}` | Правка `DRAFT/NEED_INFO` с `version` |
| GET | `/{id}/events` | История статусов |
| POST | `/{id}/submit` | Отправка / повторная отправка, `version` и опциональный `Idempotency-Key` |
| GET | `/{id}/checks` | FNS/BKI результат текущего запуска |
| POST | `/{id}/checks/run` | Запуск mock-проверок (если применимо) |
| GET | `/{id}/collateral` | Список имущества |
| POST | `/{id}/collateral` | Добавление объекта в редактируемую заявку |
| GET | `/{id}/offers` | Решения, причины и предложения |
| GET | `/{id}/explanation` | Пояснение решения (опционально через локальную LLM) |
| POST | `/{id}/accept` | Выбор `offer_id` из `OFFERED` |
| POST | `/{id}/sign/code` | Получение демо-OTP (только при включённом режиме) |
| POST | `/{id}/sign` | Подписание с `version` и шестизначным `code` |
| POST | `/{id}/disburse` | Симулированная выдача из `SIGNED` |
| POST | `/{id}/cancel` | Отказ от предложения |

## Банк (`/api/v1/bank`)

| Метод | Окончание | Назначение |
| --- | --- | --- |
| GET | `/applications` | Очередь текущих рассмотрений |
| GET | `/applications/{id}` | Карточка, проверки, DS, лимит залога |
| GET | `/applications/{id}/collateral` | Имущество по заявке |
| PATCH | `/applications/{id}/collateral/{collateral_id}` | Оценить/принять/отклонить залог |
| POST | `/applications/{id}/score` | Рассчитать и сохранить скоринг |
| POST | `/applications/{id}/evaluate` | Применить кредитную политику |
| POST | `/applications/{id}/decision` | Ручное решение (в `UNDER_REVIEW`) |
| GET | `/applications/{id}/scoring-analysis` | Расшифровка оценки для банкира |

## Примеры запросов

**Вход (используется пароль из локального `.env`):**

```json
{"email":"client_good@example.test","password":"<DEMO_CLIENT_PASSWORD>"}
```

**Создать инвестиционную заявку:**

```json
{
  "product_code": "INVESTMENT",
  "purpose": "Покупка оборудования",
  "requested_amount": "1000000.00",
  "term_months": 36,
  "financials": {
    "monthly_revenue": "1500000.00",
    "operating_expenses": "900000.00",
    "existing_debt_payments": "50000.00",
    "business_age_months": 36,
    "cash_reserve": "800000.00",
    "document_confirmed": true
  }
}
```

**Отправить черновик** (взять свежую `version` из GET):

```json
{"version":1}
```

**Банковская оценка залога:**

```json
{
  "status":"ACCEPTED",
  "assessed_value":"2000000.00",
  "has_encumbrance":false,
  "review_comment":"Демо-оценка: обременений нет"
}
```

**Запрос кода / подпись:**

```json
{"version":5}
```

```json
{"version":5,"code":"123456"}
```

`123456` — исключительно пример формата, **не реальный рабочий код**. Получить действительный можно только через `/sign/code` в локальном деморежиме.

## Коллекция запросов

[Открыть Postman Collection](api/Alfa_Navigator.postman_collection.json). Выставьте переменные `base_url`, `client_password`, `bank_password`, а после создания заявки — `application_id`, `collateral_id` и `offer_id`; коллекция не содержит секретов.

## Коды ответов

- `200/201` — успех;
- `401` — нет/истёк JWT или неверные логин/пароль;
- `403` — недостаточно прав роли;
- `404` — ресурс отсутствует или не принадлежит клиенту;
- `409` — неверное состояние, конфликт версии, ограничение процесса;
- `422` — входные данные/сумма не проходят валидацию;
- `503 DEMO_CODE_DISABLED` — OTP выключен в публичной конфигурации.

Данный документ описывает проверяемый MVP, **актуальный OpenAPI в контейнере является окончательным контрактом** для установленной версии.
