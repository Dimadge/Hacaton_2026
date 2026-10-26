# Развёртывание и обновление

## Чистая установка (основной путь для жюри)

```bash
git clone https://github.com/Dimadge/Hacaton_2026.git
cd Hacaton_2026
cp .env.example .env
# Отредактируйте .env и замените CHANGE_ME-плейсхолдеры
docker compose up -d --build
docker compose run --rm seed
docker compose ps -a
```

**Проверка:** `http://localhost:5173` (сайт), `http://localhost:8000/docs` (Swagger), `curl -i http://localhost:8000/health`, `curl -i http://localhost:8000/ready`.

Тесты: `docker compose exec -e DEMO_SIGNING_CODE_VISIBLE=true api python -m pytest -q` (временное окружение только pytest). В обычном публичном режиме демонстрационная выдача кода должна быть выключена.

**Обратите внимание:** пароли создаёт оператор в `.env`, команда `seed` использует их для создания записей. Она не изменяет пароли уже существующих пользователей. Скрипты `db/init/*.sql` выполняются автоматически PostgreSQL **только при первом создании пустого тома**. Для установки на новую чистую БД не нужно вручную запускать `001–009` второй раз.

## Обновление существующего PostgreSQL (без потери данных)

**Сначала сделайте резервную копию и проверьте, что файл ненулевого размера.**

```bash
mkdir -p ~/db_backups && chmod 700 ~/db_backups
docker compose exec -T db sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > ~/db_backups/alfa_before_upgrade.dump
ls -lh ~/db_backups/alfa_before_upgrade.dump
```

Перед применением каждого нового SQL-файла **проверьте, был ли он уже применён**. Например:

```bash
docker compose exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off' <<'SQL'
SELECT to_regclass('alfa.monthly_financials') AS m002;
SELECT to_regclass('alfa.bank_operations') AS m003;
SELECT to_regclass('alfa.application_collateral') AS m005;
SELECT column_name FROM information_schema.columns
 WHERE table_schema='alfa' AND table_name='companies' AND column_name='director_name';
SELECT to_regclass('alfa.demo_external_profiles') AS m007;
SELECT code FROM alfa.reason_codes WHERE code='COLLATERAL_LIMIT';
SELECT to_regclass('alfa.signing_codes') AS m009;
SQL
```

Если `alfa.application_collateral` отсутствует, миграция `005` должна быть применена **до запуска `db-role`**, иначе запуск остановится из-за `UndefinedTable`. Пример разового применения:

```bash
docker compose exec -T db sh -lc 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < db/init/005_application_collateral.sql
```

Точно так же применяйте **только недостающие** миграции `006`, `007`, `008`, `009` (и `002`, `003`, `004` в более старых томах, с учётом их содержимого и повторяемости). **Не запускайте все файлы без проверки состояния БД:** некоторые `CREATE TABLE` и `INSERT` неидемпотентны. Отсутствие отдельной таблицы `signing_codes` исправляется файлом `009`; отсутствие `director_name` — `006`.

Затем:

```bash
docker compose run --rm db-role
docker compose up -d --build api frontend
docker compose ps -a
```

`docker compose down -v` **удаляет весь том с данными** и не используется при обычном развёртывании/обновлении.

## Веб-адреса и прокси

**Локально:** API `localhost:8000`, frontend `localhost:5173`, `VITE_API_URL=http://localhost:8000` при сборке. Убедитесь, что `CORS_ORIGINS` включает фактический origin frontend.

**На едином публичном домене:** `VITE_API_URL=/` при сборке frontend, а обратный прокси должен направлять `/api/` на FastAPI (`127.0.0.1:8000`) и остальные запросы — на SPA (`127.0.0.1:5173`). Переменная `VITE_API_URL` **встраивается при сборке фронтенда**; после изменения выполните `docker compose up -d --build frontend`.

Тестовый адрес, который использовался командой: `http://217.71.129.139:6400`; он не гарантирует постоянной внешней доступности. На сервере НГТУ внутренний Nginx на 80 порту передавал API-запросы корректно (`HTTP 200 /api/v1/products`).

## Проверка после публикации

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:80/api/v1/products
docker compose ps -a
docker compose exec -e DEMO_SIGNING_CODE_VISIBLE=true api python -m pytest -q
```

Проверка `curl -I /` недостаточна: обязательно вызовите `/api/v1/products`, затем войдите в интерфейс под синтетическим пользователем.

## Требования безопасности до реального использования

- Не отправлять `.env` в GitHub; пользователям/жюри выдавать только синтетические данные и новые пароли для тестовой среды.
- Ротировать опубликованные или случайно показанные JWT-секреты, PostgreSQL-пароли и выданные JWT.
- Включить HTTPS; HTTP разрешается только для изолированного демонстрационного стенда без реальных данных.
- На публичном сервере держать `DEMO_SIGNING_CODE_VISIBLE=false`. При `false` подписание без реального канала доставки кода намеренно недоступно.
- Разграничить доступ к PostgreSQL и Docker, подготовить бэкапы, аудит и восстановление, контроль зависимостей.
