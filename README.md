# Альфа.Навигатор — Backend, этап 1

Демонстрационный кредитный кабинет для хакатона. Данные полностью синтетические;
оценки, тарифы и решения НЕ являются методикой Альфа-Банка.

Это **первый backend-инкремент** поверх уже существующего PostgreSQL-проекта,
а не весь MVP. Сохранены исходные файлы `db/init/001_shema.sql`,
`db/init/002_scoring_inputs.sql` и работающие Python-скрипты `app/repository.py`,
`app/demo.py`. Чтобы не ломать имеющийся репозиторий, FastAPI сейчас
расположен в `app/`; если команда позже перейдёт на монорепозиторий,
его можно перенести в `backend/app/` отдельным согласованным PR.

## 1. Что работает сейчас

- `GET /health` — жив ли HTTP-сервер, без обращения к БД.
- `GET /ready` — есть ли соединение с PostgreSQL.
- `POST /api/v1/auth/login` — вход в demo-аккаунт с Argon2-хешем и JWT.
- `GET /api/v1/products` — два кредита из таблицы `alfa.credit_products`.
- `GET /api/v1/me/company` — профиль только своей компании (`CLIENT`).
- `GET /api/v1/applications` — список своих заявок.
- `POST /api/v1/applications` — создание черновика `DRAFT` с финансовым снимком.
- `GET /api/v1/applications/{id}` — просмотр только собственной заявки.
- `PATCH /api/v1/applications/{id}` — редактирование `DRAFT` / `NEED_INFO`;
  обязательное поле `version`, новые снимки финансов вместо перезаписи истории.
- `GET /api/v1/applications/{id}/events` — журнал событий заявки из БД.

**Пока НЕ реализованы:** `submit`, `CHECKING`, реальный вызов DS-скоринга,
генерация предложений, `accept` / `sign` / `disburse`, кабинет сотрудника и
новости. Учетная запись сотрудника уже есть в seed, но банковские маршруты
будут добавлены отдельно.

## 2. Первый запуск Docker

Нужен Docker Desktop (запущенный Docker Engine) и Git. В корне проекта:

```bash
cp .env.example .env
```

В `.env` **обязательно замени** `CHANGE_ME_*` на случайные пароли:
`POSTGRES_PASSWORD`, `DB_PASSWORD`, `JWT_SECRET` (не меньше 32 символов),
`DEMO_CLIENT_PASSWORD` и `DEMO_BANK_PASSWORD` (каждый не меньше 12 символов).
Нельзя коммитить `.env` в GitHub.

Если порт 5432 занят — поменяй `POSTGRES_PORT=5433` в `.env`;
если занят 8000 — `API_PORT=8001`. В контейнерах сеть настроена автоматически.

```bash
docker compose up -d --build
# должен быть запущен db, успешно завершиться db-role и подняться api

docker compose ps
docker compose logs --tail=100 api
```

Открыть в браузере:

- Swagger API: http://localhost:8000/docs
- Проверка сервера: http://localhost:8000/health
- Проверка БД: http://localhost:8000/ready

При нестандартном `API_PORT` подставь свой порт вместо 8000.

**Один раз после первого запуска** добавить demo-учётки (повторный вызов
не меняет существующие пароли):

```bash
docker compose run --rm seed
```

Демо-email клиентов (пароль для всех — `DEMO_CLIENT_PASSWORD` из `.env`):

| Email | Сценарий на следующем этапе |
| --- | --- |
| `client_good@example.test` | Обычное одобрение S1 |
| `client_alternative@example.test` | Обратный скоринг S2 |
| `client_manual@example.test` | Ручная проверка S3 |
| `client_missing@example.test` | Дополнительные сведения S4 |
| `client_reject@example.test` | Отказ S5 |

Сотрудник: `bank@example.test`, пароль `DEMO_BANK_PASSWORD`.
Демо-аккаунты создают компании и mock-флаги, но не заявки; заявки вводятся
через API и сохраняются в PostgreSQL.

### Если PostgreSQL уже запускался раньше

Скрипты из `db/init/` **выполняются автоматически только при создании нового
тома PostgreSQL**. Если `001` был запущен до добавления `002`, колонка
`financial_profiles.cash_reserve` и таблица `monthly_financials` не появятся
сами по себе. Для существующей БД сначала:

```bash
docker compose up -d db
# проверить наличие новой таблицы:
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT to_regclass('\''alfa.monthly_financials'\'');"'
```

Если результат пустой, **ровно один раз** применить файл `002`:

```bash
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < db/init/002_scoring_inputs.sql
```

Только после этого запускай `docker compose up -d --build` для остальных
сервисов. Не используй `docker compose down -v` на БД с нужными данными:
`-v` удаляет весь том PostgreSQL.

Если в существующем томе уже присутствует SQL-роль `DB_USER`, но пароль в
`.env` поменян, `setup_role` специально НЕ меняет его автоматически —
согласуй смену пароля через администратора БД.

## 3. Проверка через Swagger

1. Открой `/docs`, выбери `POST /api/v1/auth/login`, нажми **Try it out**.
2. Отправь:

```json
{"email": "client_alternative@example.test", "password": "ПАРОЛЬ_ИЗ_ENV"}
```

3. Скопируй `access_token`. Нажми **Authorize**, вставь токен, закрой окно.
4. Вызови `GET /api/v1/me/company` — увидишь свою demo-компанию.
5. Вызови `GET /api/v1/products` — список продуктов.
6. Вызови `POST /api/v1/applications` с телом:

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

Ответ `201 Created` со статусом `DRAFT` и UUID заявки. Подставь UUID в
`GET /applications/{id}` и `GET /applications/{id}/events`.

7. Для `PATCH /applications/{id}` используй текущую `version`, например:

```json
{"version": 1, "financials": {"monthly_revenue": "1600000.00"}}
```

Номер версии должен увеличиться; предыдущий финансовый профиль хранится
в БД, а не перезаписывается. Если версия устарела → `409 VERSION_CONFLICT`.

8. Войди под другим demo-клиентом и попробуй `GET` чужого UUID — должен быть
`404 NOT_FOUND`. Вход под `bank@example.test` не даёт доступ к клиентским
эндпоинтам (`403 FORBIDDEN`).

`Authorization: Bearer <access_token>` нужен для защищённых маршрутов.
Денежные поля передаются **строками**, а не JSON-числами с плавающей точкой.

## 4. Локальные тесты без Docker

```bash
python -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

Эти тесты проверяют валидацию API, документацию, авторизацию и подпись JWT.
Они **не заменяют интеграционные тесты с реальным PostgreSQL**. Полный
E2E проверяется после локального запуска Docker.

## 5. Архитектура

```text
app/
├── main.py              # FastAPI, middleware, Swagger, /health и /ready
├── config.py            # окружение, DB URL, JWT secret
├── database.py          # единый engine и транзакция
├── core/
│   ├── errors.py        # единые 401/403/404/409/422
│   └── security.py      # Argon2, JWT, CLIENT/BANK_EMPLOYEE
├── api/v1/
│   ├── auth.py          # login
│   ├── products.py      # продукты
│   ├── me.py            # компания
│   └── applications.py  # черновики и события
├── schemas/             # Pydantic контракты
├── services/            # бизнес-операции для заявок
├── repository.py        # старый модуль SQL, сохранён и дополнен
├── setup_role.py        # создание SQL-роли с ограниченными правами
└── seed.py              # демо-пользователи и mock-профили

db/init/                 # существующая PostgreSQL-схема
Dockerfile, docker-compose.yml
requirements.txt, tests/
```

Суммы в БД хранятся как NUMERIC, в Python — `Decimal`, в JSON — строки.
Сервер проверяет владельца компании, независимо от интерфейса. История
черновиков и переходов защищается PostgreSQL-триггерами исходной схемы.

## 6. Следующие шаги (BE-05 — BE-08)

1. Согласовать контракт `ScoringInput` / `ScoringOutput` с DS.
2. Реализовать `POST /applications/{id}/submit` и переходы
   `DRAFT → SUBMITTED → CHECKING` с идемпотентностью.
3. Подключить mock ФНС/БКИ из `alfa.mock_profiles`, DS скоринг, decision rules.
4. Реализовать офферы, банк, `accept/sign/disburse`, тесты S1–S5.
5. Добавить полноценные миграции Alembic, CI и lock-файл для релиза.

Это первый работающий срез, а не заявка о полной готовности MVP.
