#!/bin/sh
# Автоматическое обновление старой локальной базы без удаления данных.
set -eu
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
# Параметры используются как отдельные аргументы (пути из репозитория).
psql_run() {
    psql -X -v ON_ERROR_STOP=1 -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
}
relation_exists() {
    [ "$(psql_run -Atqc "SELECT to_regclass('$1') IS NOT NULL")" = "t" ]
}
apply_sql() {
    echo "[db-upgrade] Applying $1"
    psql_run -f "/db/init/$1"
}

echo '[db-upgrade] Checking existing database...'
if ! relation_exists alfa.companies; then
    echo '[db-upgrade] ERROR: base schema (001) missing; PostgreSQL initialisation failed' >&2
    exit 1
fi
# 002/003/005 содержат неидемпотентные CREATE/ALTER, поэтому запускаются
# только если их ключевых объектов в старой базе ещё нет.
if ! relation_exists alfa.monthly_financials; then
    apply_sql 002_scoring_inputs.sql
fi
if ! relation_exists alfa.bank_accounts; then
    apply_sql 003_bank_operations.sql
fi
if ! relation_exists alfa.application_collateral; then
    apply_sql 005_application_collateral.sql
fi
# Эти SQL-файлы уже написаны так, что их можно повторять.
apply_sql 006_company_contact.sql
apply_sql 007_demo_external_profiles.sql
apply_sql 008_collateral_limit_reason.sql
apply_sql 009_signing_codes.sql
# Дополнительная миграция скоринга из ранее установленного патча —
# только если она реально есть в текущей копии проекта.
if [ -f /db/migrations/20261026_bank_scoring.sql ]; then
    if [ "$(psql_run -Atqc "SELECT EXISTS (SELECT 1 FROM alfa.scoring_rules WHERE rule_version='rules-v2-bank')")" != "t" ]; then
        echo '[db-upgrade] Applying bank scoring rule migration'
        psql_run -f /db/migrations/20261026_bank_scoring.sql
    fi
fi
# Не перезапускаем 004 с массовыми операциями на существующей БД.
# При первой инициализации новой БД его уже выполняет postgres entrypoint.
for tbl in alfa.users alfa.companies alfa.bank_accounts alfa.bank_operations alfa.bank_history_coverage alfa.application_collateral alfa.signing_codes; do
    if ! relation_exists "$tbl"; then
        echo "[db-upgrade] ERROR: Missing table $tbl" >&2
        exit 1
    fi
done
column_exists() {
    [ "$(psql_run -Atqc "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='alfa' AND table_name='$1' AND column_name='$2')")" = "t" ]
}
column_exists companies director_name || { echo '[db-upgrade] director_name not found' >&2; exit 1; }
column_exists users phone || { echo '[db-upgrade] users.phone not found' >&2; exit 1; }
echo '[db-upgrade] Schema is ready.'
