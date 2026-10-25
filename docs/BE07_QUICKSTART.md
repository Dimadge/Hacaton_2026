# Альфа.Навигатор — BE-07 (первый релиз: политика + кабинет банка)

> Учебный MVP. **Нет реального кредитного решения банка.** Используются только синтетические данные ФНС/БКИ. Скоринг от DS пока не подключён: **одобрение без скоринга запрещено**.

## Состав обновления

- `app/api/v1/bank.py`: очередь, банковская карточка, запуск policy, ручные действия.
- `app/services/decision_policy.py`: чистые правила приоритетов.
- `app/services/decisions.py`: транзакции и сохранение кредитных решений в существующей PostgreSQL.
- `app/schemas/decision.py`: строгие DTO, проверка версий и офферов.
- `app/api/v1/applications.py`: GET /applications/{id}/offers для клиента.
- `app/main.py`: регистрация банковского роутера.
- `tests/decisions/test_be07.py`: тесты сценариев, ролей, версий, лимитов.

Нет изменений существующих таблиц и SQL-миграций. Для истории `alfa.application_events` используется действующий триггер; двойная запись не создаётся.

## Установка

Из **корня** репозитория `Hacaton_2026` в ветке `feature/backend-fastapi`:

```bash
# Убедитесь, что изменения BE05 и BE06 уже установлены, нет незакоммиченных изменений.
git status
unzip -o ~/Downloads/alfa_navigator_BE07_patch.zip -d .
docker compose up -d --build
docker compose exec api python -m pytest -q
```

При полной установленной последовательности stage1 + BE05 + BE06 + BE07 на используемом тестовом окружении: **62 passed**. Проверка с реальной PostgreSQL выполняется далее через Swagger, а не заменяется юнит-тестами.

**Не выполняйте** `docker compose down -v`, иначе будет удалён volume с базой. `.env` не входит в patch и не должен попадать в Git.

## Проверка на УЖЕ СОЗДАННОЙ заявке

Твоя заявка `fbf0be75-eb7b-491f-bd3c-8c0111c5b564` находится в `CHECKING`, ФНС `active`, БКИ `good`.

1. Открой http://localhost:8000/docs.
2. Если Swagger забывает авторизацию, вызови `POST /api/v1/auth/login` с **банковским** аккаунтом `bank@example.test` и паролем `DEMO_BANK_PASSWORD` из `.env`. Скопируй `access_token` и нажми `Authorize` → вставь токен → `Authorize` → `Close`.
3. `GET /api/v1/bank/applications` → `Try it out` → `Execute`. Найди свою заявку в списке со статусом `CHECKING`.
4. `GET /api/v1/bank/applications/{application_id}` → вставь UUID → `Execute`. Должны быть `verification_results`: `FNS=active`, `BKI=good`; `scoring_ready=false`.
5. `POST /api/v1/bank/applications/{application_id}/evaluate` → вставь UUID → `Execute`. Ожидается HTTP 200 и `next_step: "SCORING_PENDING"`. **Статус остаётся CHECKING** — без скоринга положительное решение не выставляется.

## Как проверить реальный переход UNDER_REVIEW → NEED_INFO

Используй **новую** заявку для демонстрационного клиента `client_manual@example.test`, не текущую заявку `client_good`.

1. В `POST /auth/login` войди как `client_manual@example.test` с `DEMO_CLIENT_PASSWORD`. Авторизуй Swagger этим JWT.
2. Создай через `POST /api/v1/applications` черновик, например:

```json
{
  "product_code": "INVESTMENT",
  "purpose": "Покупка оборудования",
  "requested_amount": "3000000.00",
  "term_months": 36,
  "financials": {
    "monthly_revenue": "1500000.00",
    "operating_expenses": "900000.00",
    "existing_debt_payments": "150000.00",
    "business_age_months": 36,
    "cash_reserve": "800000.00",
    "document_confirmed": true
  }
}
```

3. Скопируй **новый** `id`, отправь через `POST /api/v1/applications/{id}/submit`, body `{ "version": 1 }`. Mock ФНС/BKI сохранятся автоматически (`minor_delay` для этого клиента).
4. Перезайди в Swagger банковским `bank@example.test`, авторизуй новый токен.
5. `POST /api/v1/bank/applications/{id}/evaluate`: статус изменится в `UNDER_REVIEW` (версия обычно 4).
6. `POST /api/v1/bank/applications/{id}/decision`, body (проверь актуальную версию из GET перед отправкой):

```json
{
  "version": 4,
  "action": "REQUEST_INFO",
  "reason_codes": ["CREDIT_HISTORY_DELAY"],
  "comment": "Демо: запросить дополнительные сведения о просрочке",
  "offers": []
}
```

7. Ответ должен быть `NEED_INFO`, а GET /events покажет переходы CHECKING→UNDER_REVIEW→NEED_INFO.
8. Для проверки роли попробуй вызвать любой `/bank/...` с JWT **клиента**: ожидаем `403 FORBIDDEN`.

## Проверка отказа

Создай и отправь заявку от `client_reject@example.test` (БКИ `critical`) и оцени её банковским `POST /evaluate`: ожидается `REJECTED` и `CREDIT_HISTORY_CRITICAL`. Повторный `/evaluate` на уже завершённой заявке вернёт HTTP 409; второе решение не создастся.

## Почему нельзя пока получить OFFERED

В существующей SQL-схеме триггер `alfa.guard_offer` **обязательно** требует сохранённый `scoring_results` для текущего `evaluation_run` и проверяет: продукт, ставку, лимит платежа, сумму, срок, аннуитет. BE-07 это правило не обходит. В Swagger `POST /bank/.../decision` с `action="APPROVE"` до скоринга вернёт `409 SCORING_PENDING`. `GET /applications/{id}/offers` сейчас покажет пустые офферы и/или последнее доступное решение. После получения DS-модуля BE интегрирует расчёт и выпуск офферов.

## Контракт для DS

В текущем `app/scoring/contracts.py` уже есть `ScoringInput`, `ScoringOutput`, `OfferCandidate` (денежные поля `Decimal`, не float). Бэкенд ждёт `score_application(ScoringInput) -> ScoringOutput`. Перед сохранением в `alfa.scoring_results` дополнительно согласовать расчёт `score_raw`, `cash_flow`, `requested_payment`, `factors` и связь с `rule_version`. **Нельзя заполнять их выдуманными числами для реального прохождения сценария.**

## Сохранение изменений

```bash
git add app/main.py app/api/v1/applications.py app/api/v1/bank.py app/schemas/decision.py \
        app/services/decisions.py app/services/decision_policy.py tests/decisions/ docs/BE07_QUICKSTART.md
git commit -m "feat(backend): add bank queue and preliminary decisions"
git push origin feature/backend-fastapi
```

## Важные ограничения

- В этой версии `/bank/.../evaluate` запускается явно сотрудником; автоматический вызов после CHECKING будет включён после интеграции с DS и оркестрации конвейера.
- Ветку `NEED_INFO → CHECKING` с повторной отправкой клиента дорабатываем вместе с итоговым workflow в следующем этапе.
- Не раскрывайте JWT-токен на скриншотах; после утечки демо-токена полезно сменить `JWT_SECRET` и перезапустить API.
