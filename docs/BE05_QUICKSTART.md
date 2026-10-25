# Альфа.Навигатор — BE-05: отправка заявки

**Этап 2 поверх работающего проекта.** Реализован только путь `DRAFT → SUBMITTED → CHECKING`.
Скоринг, ФНС/БКИ и выдача кредитного решения будут подключаться на BE-06/07.
База `alfa` и её таблицы **не заменяются**, миграции для BE-05 не нужны.

## Изменённые файлы

- `app/services/workflow.py` — atomic submit, создание `evaluation_runs`, idempotency.
- `app/services/applications.py` — выбор `financial_profile_id` для снимка.
- `app/schemas/application.py` — `ApplicationSubmit`, `SubmissionOut`.
- `app/api/v1/applications.py` — `POST /{application_id}/submit`.
- `tests/workflow/test_submit.py` — тесты переходов, version, replay и API.
- `Dockerfile` — тесты и pytest.ini включены в контейнер, `docker compose exec api python -m pytest -q` теперь находит их.

## Обновление своего репозитория на Mac

Убедись, что находишься в корне существующего репозитория `Hacaton_2026` на ветке
`feature/backend-fastapi` и сохрани незакоммиченные изменения (`git status`).

Патч ZIP содержит пути **от корня проекта** (`app/`, `tests/`, `Dockerfile`, `docs/`).
Скопируй скачанный архив в корень проекта, затем:

```bash
git branch --show-current
unzip -o alfa_navigator_BE05_patch.zip -d .
docker compose up -d --build
# Внимание: НЕ используй 'docker compose down -v' — это удалит PostgreSQL volume.
docker compose exec api python -m pytest -q
```

После сборки открой http://localhost:8000/docs.

## Тест через Swagger

1. В `POST /api/v1/auth/login` войди под `client_good@example.test` с собственным demo-паролем.
2. Нажми **Authorize** и вставь новый JWT-токен.
3. `GET /api/v1/applications` — найди заявку со статусом `DRAFT` и запомни её UUID, `version` (обычно 1).
4. `POST /api/v1/applications/{application_id}/submit`:
   - `application_id` — UUID найденной заявки;
   - заголовок **Idempotency-Key** — например, `first-submit-001` (для каждой новой подачи придумай новое значение);
   - `Request body`: `{ "version": 1 }` (или актуальный номер из GET).
5. Нажми Execute. Ожидается `HTTP 200`, тело вида:

```json
{
  "id": "uuid-заявки",
  "status": "CHECKING",
  "version": 3,
  "evaluation_run_id": "uuid-цикла-проверки"
}
```

6. `GET /api/v1/applications/{application_id}` — статус `CHECKING`, версия 3 (при версии 1 до подачи).
7. `GET /api/v1/applications/{application_id}/events` — появятся последовательно `CREATE (DRAFT)`, `STATUS_CHANGE (SUBMITTED)`, `STATUS_CHANGE (CHECKING)`.
8. **Повтори** тот же `POST` с прежним `Idempotency-Key` и прежним телом. Получишь тот же `200` и тот же `evaluation_run_id`. Событий больше не станет.
9. Если отправишь тот же submit без ключа, сервер вернёт `409 VERSION_CONFLICT` (заявка уже в CHECKING).

### Что сохраняется

- `loan_applications`: статус `CHECKING`, номер версии +2.
- `application_events`: две записи перехода, **созданные триггером PostgreSQL**, не отдельными INSERT приложения.
- `evaluation_runs`: один запуск проверки с версией подачи, полным финансовым снимком и снимком тарифа. `scoring_results` **пока пусто** — модуль DS ещё не подключён.
- `idempotency_keys`: один результат для явно указанного ключа.

Все четыре операции выполняются в **одной транзакции** на стороне FastAPI. При неуспехе изменения откатываются целиком.

## После проверки

```bash
git status
git add app/api/v1/applications.py app/services/applications.py app/services/workflow.py app/schemas/application.py \
  Dockerfile tests/workflow/test_submit.py docs/BE05_QUICKSTART.md
git commit -m "feat(backend): add atomic application submit workflow"
git push origin feature/backend-fastapi
```

Сюда нельзя включать `.env`, приватные данные, JWT и пароли.

## Ограничения

- Запрос заканчивается на `CHECKING`; решения `OFFERED/REJECTED/NEED_INFO` появятся после BE-06/07.
- Юнит-тесты используют имитацию SQLAlchemy connection. Они НЕ проверяют настоящие триггеры PostgreSQL; это необходимо проверить локально в Swagger (особенно события и транзакцию).
- На одном и том же запросе `Idempotency-Key` и версия **должны оставаться прежними**, иначе ожидается `409 IDEMPOTENCY_CONFLICT`.
