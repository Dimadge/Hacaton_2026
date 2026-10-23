# PostgreSQL — Альфа.Навигатор

PostgreSQL 16 запускается `docker compose up -d db`. Схема `alfa` создаётся
`db/init/001_shema.sql` при **первом** создании тома. Файл
`db/init/002_scoring_inputs.sql` добавляет финансовый резерв и помесячные
показатели. Поскольку init-скрипты не миграции, они не запускаются на
уже существующей БД после рестарта. Порядок обновления сохранённого тома
описан в корневом README.

Создание клиентской SQL-роли: `docker compose up db-role`.
Демо-компании и пользователей добавляет `docker compose run --rm seed`.
Основной API запускается `docker compose up -d --build`.
Демо-финансы вводятся через `POST /api/v1/applications`.

**Не использовать** `docker compose down -v` при необходимости сохранить
данные PostgreSQL; достаточно `docker compose down`.
