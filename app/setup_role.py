"""Локальная dev-настройка SQL-роли: права + пароль из .env.

Этот файл предназначен для Docker Compose в учебной среде: если DB_PASSWORD
изменён в .env, учётная запись БД синхронизируется до запуска API.
"""
import psycopg
from psycopg import sql

from .config import database_url, required


def main():
    u = database_url(admin=True)
    name, password = required("DB_USER"), required("DB_PASSWORD")
    if name == u.username:
        raise ValueError("DB_USER должен отличаться от POSTGRES_USER")

    with psycopg.connect(host=u.host, port=u.port, dbname=u.database,
                         user=u.username, password=u.password) as conn:
        exists = conn.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=%s",
            (name,),
        ).fetchone()
        if exists is None:
            conn.execute(sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
            ).format(sql.Identifier(name), sql.Literal(password)))
        else:
            if any(exists):
                raise ValueError("Существующая роль обладает административными правами")
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(name), sql.Literal(password)))

        queries = [
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(u.database), sql.Identifier(name)),
            sql.SQL("GRANT USAGE ON SCHEMA alfa TO {}").format(sql.Identifier(name)),
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA alfa TO {}").format(sql.Identifier(name)),
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA alfa TO {}").format(sql.Identifier(name)),
            sql.SQL("GRANT INSERT ON alfa.companies, alfa.users, alfa.loan_applications, alfa.financial_profiles, alfa.application_documents, alfa.mock_profiles, alfa.evaluation_runs, alfa.verifications, alfa.scoring_results, alfa.scoring_result_reasons, alfa.credit_decisions, alfa.decision_reasons, alfa.credit_offers, alfa.application_events, alfa.idempotency_keys, alfa.monthly_financials TO {}").format(sql.Identifier(name)),
            sql.SQL("GRANT UPDATE ON alfa.loan_applications, alfa.users, alfa.mock_profiles, alfa.idempotency_keys TO {}").format(sql.Identifier(name)),
            sql.SQL("GRANT SELECT, INSERT, UPDATE ON alfa.application_collateral TO {}").format(sql.Identifier(name)),
            sql.SQL("GRANT INSERT, UPDATE ON alfa.signing_codes TO {}").format(sql.Identifier(name)),
        ]
        for query in queries:
            conn.execute(query)
    print("SQL-роль настроена и пароль синхронизирован с DB_PASSWORD.")


if __name__ == "__main__":
    main()
