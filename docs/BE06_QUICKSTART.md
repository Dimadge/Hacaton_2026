# Альфа.Навигатор — BE-06: локальные проверки ФНС/БКИ

## Что реализовано

- Mock ФНС и БКИ **только на синтетических данных из `alfa.mock_profiles`**, без реальных HTTP-запросов.
- При `POST /api/v1/applications/{application_id}/submit` (новая заявка) две проверки автоматически сохраняются в таблицу `alfa.verifications` **в той же DB-транзакции** вместе с результатом submit.
- Для заявки, уже отправленной в BE-05 и стоящей в `CHECKING`, доступен **`POST /api/v1/applications/{application_id}/checks/run`**. Запрос **без body**, достаточно авторизации.
- `GET /api/v1/applications/{application_id}/checks` показывает сохранённые результаты; чтение **не выполняет** новые проверки.
- Для каждой пары `evaluation_run_id + source` существует не более одной записи. История неизменяема. Повтор `checks/run` сохраняет прежние ответы, даже если синтетический флаг затем изменился.
- Проверки привязаны к **последнему** `evaluation_run` заявки. При новой законной подаче после NEED_INFO начнётся отдельный цикл и отдельные результаты.
- Если mock-профиль компании отсутствует — обе проверки получают `unknown`, а НЕ `active` или `good`.
- `reason_codes`: REGISTRY_INACTIVE, REGISTRY_MISMATCH, CREDIT_HISTORY_DELAY, CREDIT_HISTORY_CRITICAL, UNKNOWN_VERIFICATION. Статус пока **CHECKING**; ни кредитного решения, ни расчёта score нет.
- `app/scoring/contracts.py` и `app/services/scoring_adapter.py` подготавливают строгий интерфейс входа/выхода DS. Сама реализация `score_application` ещё **не подключена**.

## Как добавить патч поверх работающего BE-05 (Mac)

Работай в **том же git-репозитории** на ветке `feature/backend-fastapi`. Сначала проверь, что не потеряешь свои незакоммиченные правки:

```bash
git branch --show-current
git status
```

Скачай `alfa_navigator_BE06_patch.zip`, затем **из корня `Hacaton_2026`** выполни:

```bash
unzip -o ~/Downloads/alfa_navigator_BE06_patch.zip -d .
docker compose up -d --build
docker compose exec api python -m pytest -q
```

Если архив сохранён под другим именем или не в Downloads — исправь путь. Ожидаемый итог локального набора тестов: **35 passed**. Все тесты используют fake SQL connections; их необходимо дополнить проверкой на твоей реальной PostgreSQL через Swagger.

**Не используй** `docker compose down -v` и не удаляй том Postgres — это сотрёт существующие заявки. Файл `.env` не нужно менять или коммитить. **Миграций и новых таблиц не требуется:** `mock_profiles`, `evaluation_runs`, `verifications` уже есть в `001_shema.sql`.

## Проверка через Swagger: твоя существующая заявка

1. Открой <http://localhost:8000/docs>.
2. При необходимости `POST /api/v1/auth/login` под `client_good@example.test` и кнопка **Authorize** с новым JWT.
3. `GET /api/v1/applications` — убедись, что заявка `fbf0be75-eb7b-491f-bd3c-8c0111c5b564` сейчас в `CHECKING`.
4. Вызови **`POST /api/v1/applications/{application_id}/checks/run`**:
   - `application_id` = `fbf0be75-eb7b-491f-bd3c-8c0111c5b564`
   - `Request body` отсутствует
   - **Execute**
5. Ожидается HTTP 200 и JSON с `completed: true`, `application_status: CHECKING`, `checks` с `FNS: active`, `BKI: good`, `reason_codes: []`. Это результат для синтетической компании `client_good`, пока её mock-флаги не меняли.
6. Вызови **`GET /api/v1/applications/{application_id}/checks`** с тем же UUID — увидишь те же сохранённые `id`, `run_id`, `source`, `result`, `checked_at`.
7. Повтори `POST .../checks/run` — вернутся те же `checks`, **без новых строк**.
8. По `GET /api/v1/applications/{application_id}/events` убедись, что переходов в `OFFERED` или `REJECTED` пока не появилось.

### Пример сокращённого ответа (не копировать как фактический идентификатор)

```json
{
  "application_id": "fbf0be75-eb7b-491f-bd3c-8c0111c5b564",
  "evaluation_run_id": "<uuid-цикла>",
  "application_status": "CHECKING",
  "completed": true,
  "checks": [
    {"id":"<uuid>","run_id":"<uuid-цикла>","source":"FNS","result":"active","payload":{"provider":"fns_local_mock","synthetic":true,"mock_profile_present":true},"checked_at":"<UTC timestamp>"},
    {"id":"<uuid>","run_id":"<uuid-цикла>","source":"BKI","result":"good","payload":{"provider":"bki_local_mock","synthetic":true,"mock_profile_present":true},"checked_at":"<UTC timestamp>"}
  ],
  "reason_codes": []
}
```

### Что важно

- `completed: true` означает **обе mock-проверки сохранены**, а не то, что кредит одобрен.
- `client_manual` даёт БКИ=`minor_delay` / причину `CREDIT_HISTORY_DELAY`.
- `client_reject` даёт БКИ=`critical` / причину `CREDIT_HISTORY_CRITICAL`.
- `client_missing` в seed имеет ФНС=`active`, БКИ=`good`; его ветка NEED_INFO связана с отсутствующим подтверждением документа и будет реализована в BE-07.
- Только клиент-владелец может видеть проверки: чужая компания получает 404, банк через клиентские endpoints — 403.
- Запросы ФНС/БКИ НЕ обращаются к настоящим государственным системам и НЕ определяют реальную кредитоспособность.

## Для ML / DS разработчика

Контракт `ScoringInput` находится в `app/scoring/contracts.py`:
`monthly_revenue`, `operating_expenses`, `existing_debt_payments`, `business_age_months`, `requested_amount`, `term_months`, `demo_rate`, `credit_history_flag`, `company_registry_flag`.

`ScoringOutput` содержит `score`, `risk_level`, `max_new_monthly_payment`, `decision_hint`, `candidates`, `reason_codes`, `rule_version`. Деньги и ставка — `Decimal`, не `float`. Не менять схемы без согласования с Backend.

Backend подготовил `build_scoring_input(conn, run_id)` из сохранённых snapshots и verifications. После получения реального `score_application(input)` потребуется отдельный этап BE-07 для хранения `scoring_results`, применения кредитной политики, создания решений и офферов.

## Git

```bash
git status
git add app/main.py app/api/v1/applications.py app/integrations/ app/scoring/ \
  app/schemas/checks.py app/services/checks.py app/services/scoring_adapter.py \
  tests/checks/ tests/workflow/test_submit.py docs/BE06_QUICKSTART.md
git commit -m "feat(backend): add FNS and BKI mock verifications"
git push origin feature/backend-fastapi
```

Ни пароли из `.env`, ни JWT-токены не загружай в репозиторий.
