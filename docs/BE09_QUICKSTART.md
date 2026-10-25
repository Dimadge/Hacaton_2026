# BE-09 — повторная подача после NEED_INFO

## Назначение

Завершить ветку из MVP `NEED_INFO → CHECKING` после запроса сведений сотрудником банка. Используется **существующий** `POST /api/v1/applications/{application_id}/submit`, отдельный endpoint не создаём.

Этот релиз **не включает ML-скоринг**, не одобряет кредит, не подключается к реальным ФНС/БКИ и не загружает настоящие документы. Сведения — синтетические, система — учебная.

### Изменения

- `app/schemas/application.py` — новое необязательное поле `clarification` (10–2000 символов) в `ApplicationSubmit`.
- `app/services/workflow.py` — первая подача DRAFT работает по-прежнему; для NEED_INFO создаётся новый run и выполняется **разрешённый схемой БД прямой переход NEED_INFO → CHECKING**. Данные старых запусков не изменяются. Требуются новые данные анкеты и/или новое пояснение.
- `app/api/v1/applications.py` — передаёт пояснение в workflow; ФНС/БКИ выполняются и при повторной подаче.
- `app/services/checks.py` — повтор уже выполненных проверок ничего не перезаписывает, в том числе после изменения статуса заявки.
- `app/services/decisions.py` + `app/schemas/decision.py` — сотрудник видит последнее `client_clarification` через `GET /api/v1/bank/applications/{application_id}`.
- `tests/workflow/test_resubmit.py` и дополнение `tests/checks/test_mock_checks.py` — тесты.

**Новых таблиц и миграций не нужно.** Для уточнения без правки финансов текст сохраняется в `evaluation_runs.input_snapshot` нового run; никаких загруженных файлов/доказательств оплаты он не заменяет.

## Установка (Mac, из корня существующего репозитория)

1. Убедиться, что BE-08 уже установлен, ветка — `feature/backend-fastapi` и несохранённые изменения не будут перезаписаны.
2. Скачать `alfa_navigator_BE09_patch.zip` в `~/Downloads`.
3. В терминале VS Code выполнить:

```bash
git status
unzip -o ~/Downloads/alfa_navigator_BE09_patch.zip -d .
docker compose up -d --build
docker compose exec api python -m pytest -q
```

В тестовой среде выполнено **96 passed**; полную проверку на вашей PostgreSQL нужно пройти самостоятельно. **Не выполняйте** `docker compose down -v`. Файл `.env` этот ZIP не содержит. Не публикуйте JWT.

## Проверка на твоей существующей заявке

Текущая учебная заявка: `0cda98d2-6d1d-4d8e-b1da-a42df03b0780`; последняя зафиксированная версия `5`, статус `NEED_INFO` (после запроса сведений сотрудником). Если версия у тебя уже изменилась, возьми актуальную из `GET /api/v1/applications/{id}`.

1. Swagger `http://localhost:8000/docs` → войди под `client_manual@example.test` с `DEMO_CLIENT_PASSWORD` из `.env`, затем `Authorize` клиентским JWT. **Банковский токен использовать нельзя**.
2. (Рекомендуется) `GET /api/v1/applications/{id}` → посмотри текущие `status` и `version`.
3. `POST /api/v1/applications/{id}/submit`, поле `application_id`: `0cda98d2-6d1d-4d8e-b1da-a42df03b0780`, заголовок `Idempotency-Key`: `manual-clarification-001`. Тело:

```json
{
  "version": 5,
  "clarification": "Демонстрационное пояснение: прошу повторно рассмотреть сведения о просрочке."
}
```

4. Нажми Execute. Ожидаем HTTP **200**, `status: CHECKING`, `version: 6`, **новый** `evaluation_run_id`. Он должен отличаться от предыдущего.
5. `GET /api/v1/applications/{id}/events`: ожидаем добавление ровно одного события `NEED_INFO → CHECKING`, версия 6.
6. `GET /api/v1/applications/{id}/checks`: новые результаты `FNS=active`, `BKI=minor_delay`, `completed=true`, связанные с новым `evaluation_run_id`.
7. Войди сотрудником `bank@example.test`, замени токен в Authorize. `GET /api/v1/bank/applications/{id}` вернёт `client_clarification` (пояснение клиента).
8. `POST /api/v1/bank/applications/{id}/evaluate`: поскольку тестовый БКИ по-прежнему `minor_delay`, ожидаем `UNDER_REVIEW`, и версия станет 7.

### Альтернатива — изменение анкеты перед повторной подачей

Вместо пояснения можно отредактировать реальные **учебные** финансовые данные через `PATCH /api/v1/applications/{id}` (только когда статус NEED_INFO). Например, если версия 5:

```json
{"version":5,"financials":{"cash_reserve":"350000.00"}}
```

Получить новую версию из PATCH (обычно 6), затем `POST /submit` с `{"version":6}`. Версия после resubmit станет обычно 7. Используй **либо** путь с пояснением, **либо** путь с PATCH: не требуется выполнять оба.

### Ошибки и ограничения

| Ответ | Значение |
|---|---|
| `401` | JWT отсутствует/истёк; заново зайти |
| `403` | Вход сотрудником банка вместо клиента |
| `404` | Чужая/несуществующая заявка |
| `409 NO_NEW_INFORMATION` | Для NEED_INFO нет изменённых данных или нового пояснения |
| `409 VERSION_CONFLICT` | Указана неактуальная версия |
| `409 IDEMPOTENCY_CONFLICT` | Один и тот же ключ использован для другого тела запроса |
| `422` | Неверный JSON или слишком короткое/длинное пояснение |

`minor_delay` не исчезает от текста пояснения: это фиксированный mock-профиль, а не реальное исправление кредитной истории. Нет интерфейса прикрепления подтверждающих файлов; полноценное исправление подтверждающих документов — отдельная задача. Скоринг/офферы/выдача по-прежнему ожидают интеграции DS.
