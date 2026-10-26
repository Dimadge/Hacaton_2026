"""Повторяемое заполнение Hacaton_2026 тестовыми данными.

Запуск: docker compose run --rm --build seed
- 10 клиентов и один сотрудник банка;
- синхронизация паролей ТОЛЬКО известных демо-учёток с .env;
- телефон и ФИО руководителя (ФИО не затирает существующее);
- если у демокомпании ещё нет операций, создаётся демосчёт
  и 36 синтетических операций за три завершённых месяца.
- существующие банковские операции, заявки и связи пользователей с компаниями не меняются.
- действующие mock-профили не перезаписываются.

Требует таблиц из db/init/003_bank_operations.sql и полей из
 db/init/006_company_contact.sql в уже созданной PostgreSQL.
Только для локальной/учебной среды, не для production.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from argon2 import PasswordHasher
from sqlalchemy import text

from .config import required
from .database import make_engine


# Код, ИНН, название компании, отрасль, ФИО, телефон, mock-ФНС, mock-БКИ
CLIENTS = (
    ("client_good", "9912345601", "Демо: Мастерская", "MANUFACTURING", "Иванов Алексей Сергеевич", "+79990001001", "active", "good"),
    ("client_alternative", "9912345602", "Демо: Оборудование", "MANUFACTURING", "Петров Михаил Андреевич", "+79990001002", "active", "good"),
    ("client_manual", "9912345603", "Демо: Магазин", "TRADE", "Смирнова Анна Викторовна", "+79990001003", "active", "minor_delay"),
    ("client_missing", "9912345604", "Демо: Кафе", "FOOD", "Кузнецов Дмитрий Игоревич", "+79990001004", "active", "good"),
    ("client_reject", "9912345605", "Демо: Сервис", "SERVICES", "Соколова Елена Павловна", "+79990001005", "active", "critical"),
    ("client_stable", "9912345606", "Демо: Стройкомплект", "CONSTRUCTION", "Васильев Роман Олегович", "+79990001006", "active", "good"),
    ("client_growth", "9912345607", "Демо: Логистика", "TRANSPORT", "Морозов Артём Николаевич", "+79990001007", "active", "good"),
    ("client_seasonal", "9912345608", "Демо: Туризм", "SERVICES", "Новикова Мария Денисовна", "+79990001008", "active", "minor_delay"),
    ("client_inactive", "9912345609", "Демо: Поставки", "TRADE", "Фёдоров Павел Евгеньевич", "+79990001009", "inactive", "good"),
    ("client_unknown", "9912345610", "Демо: ИТ", "IT", "Орлова Наталья Сергеевна", "+79990001010", "unknown", "unknown"),
)


def _three_closed_months():
    first = date.today().replace(day=1)
    months = []
    for _ in range(3):
        first = (first - timedelta(days=1)).replace(day=1)
        months.append(first)
    return list(reversed(months))


def _seed_missing_operations(conn, company_id, user_id, code, inn, index):
    """Не изменяем/не дублируем историю, если по компании уже есть операции."""
    has_operations = conn.scalar(text("""
        SELECT EXISTS (
            SELECT 1
            FROM alfa.bank_accounts a
            JOIN alfa.bank_operations o ON o.account_id = a.id
            WHERE a.company_id = :company_id
        )
    """), {"company_id": company_id})
    if has_operations:
        return 0

    # Существующий счет компании (даже пока без операций) используем повторно.
    account = conn.execute(text("""
        SELECT id, company_id
        FROM alfa.bank_accounts
        WHERE company_id = :company_id
        ORDER BY opened_at, id
        LIMIT 1
    """), {"company_id": company_id}).mappings().first()

    if account is None:
        external_id = f"DEMO-ACCOUNT-{inn}"
        conn.execute(text("""
            INSERT INTO alfa.bank_accounts (company_id, external_id, opened_at)
            VALUES (:company_id, :external_id, :opened_at)
            ON CONFLICT (external_id) DO NOTHING
        """), {
            "company_id": company_id,
            "external_id": external_id,
            "opened_at": date(2023, 1, 1),
        })
        account = conn.execute(text("""
            SELECT id, company_id FROM alfa.bank_accounts
            WHERE external_id = :external_id
        """), {"external_id": external_id}).mappings().one()
    if account["company_id"] != company_id:
        raise ValueError("Демосчёт связан с другой компанией")

    count = 0
    for month_number, month in enumerate(_three_closed_months()):
        for item in range(12):
            if item < 5:
                direction, category = "IN", "SALES"
                amount = Decimal(110000 + index * 15000 + month_number * 4000 + item * 3000)
            elif item < 10:
                direction, category = "OUT", "OPERATING"
                amount = Decimal(45000 + index * 4000 + item * 900)
            elif item == 10:
                direction, category = "OUT", "OWN_TRANSFER"
                amount = Decimal("12000.00")
            else:
                direction, category = "IN", "LOAN"
                amount = Decimal("20000.00")

            operation_id = f"DEMO-{code}-{month:%Y%m}-{item:02d}"
            booked = datetime(month.year, month.month, 3 + item * 2, 12, tzinfo=timezone.utc)
            result = conn.execute(text("""
                INSERT INTO alfa.bank_operations
                    (account_id, external_id, booked_at, direction, category,
                     amount, description, imported_by)
                VALUES
                    (:account_id, :external_id, :booked_at, :direction, :category,
                     :amount, :description, :imported_by)
                ON CONFLICT (account_id, external_id) DO NOTHING
            """), {
                "account_id": account["id"],
                "external_id": operation_id,
                "booked_at": booked,
                "direction": direction,
                "category": category,
                "amount": amount,
                "description": f"Учебная операция {category} ({code})",
                "imported_by": user_id,
            })
            count += result.rowcount

        conn.execute(text("""
            INSERT INTO alfa.bank_history_coverage (account_id, month, confirmed_by)
            VALUES (:account_id, :month, :confirmed_by)
            ON CONFLICT (account_id, month) DO NOTHING
        """), {
            "account_id": account["id"],
            "month": month,
            "confirmed_by": user_id,
        })
    return count


def main():
    client_password = required("DEMO_CLIENT_PASSWORD")
    bank_password = required("DEMO_BANK_PASSWORD")
    if min(len(client_password), len(bank_password)) < 12:
        raise ValueError("Демо-пароли должны содержать не менее 12 символов")

    hasher = PasswordHasher()
    engine = make_engine(admin=True)
    new_operations = 0
    try:
        with engine.begin() as conn:
            for index, (code, inn, name, industry, director, phone, fns, bki) in enumerate(CLIENTS):
                email = f"{code}@example.test"

                # У ранее созданного демопользователя может быть ДРУГАЯ компания,
                # поскольку предыдущие версии seed и SQL-заготовки использовали
                # разные ИНН. Его company_id менять нельзя: на него ссылаются
                # заявки, банковские счета и другие данные.
                existing = conn.execute(text("""
                    SELECT u.id, u.role::text AS role, u.company_id,
                           c.inn AS company_inn
                    FROM alfa.users u
                    LEFT JOIN alfa.companies c ON c.id = u.company_id
                    WHERE u.email = :email
                    FOR UPDATE OF u
                """), {"email": email}).mappings().first()

                if existing:
                    if existing["role"] != "CLIENT" or not existing["company_id"] or not existing["company_inn"]:
                        raise ValueError(
                            f"Email {email} занят не клиентской учётной записью с компанией; "
                            "автоматически менять её роль нельзя"
                        )
                    user_id = existing["id"]
                    company_id = existing["company_id"]
                    effective_inn = existing["company_inn"]
                    if effective_inn != inn:
                        print(
                            f"[seed] {email}: сохраняю существующую привязку "
                            f"к компании (ИНН {effective_inn}), "
                            "не переназначаю заявки и счета"
                        )
                    # ФИО заполняем только если оно ещё не установлено.
                    conn.execute(text("""
                        UPDATE alfa.companies
                        SET director_name = COALESCE(director_name, :director)
                        WHERE id = :company_id
                    """), {"director": director, "company_id": company_id})

                    # Синхронизируем ТОЛЬКО этот явно указанный тестовый email.
                    conn.execute(text("""
                        UPDATE alfa.users
                        SET password_hash = :password_hash,
                            phone = :phone,
                            active = true
                        WHERE id = :user_id AND role = 'CLIENT'
                    """), {
                        "user_id": user_id,
                        "password_hash": hasher.hash(client_password),
                        "phone": phone,
                    })
                else:
                    # Для нового демопользователя создаём компанию с указанным
                    # ИНН. При повторном запуске запись остаётся прежней.
                    conn.execute(text("""
                        INSERT INTO alfa.companies
                            (name, inn, industry, registered_at, director_name)
                        VALUES (:name, :inn, :industry, :registered_at, :director_name)
                        ON CONFLICT (inn) DO UPDATE
                        SET director_name = COALESCE(
                            alfa.companies.director_name, EXCLUDED.director_name
                        )
                    """), {
                        "name": name, "inn": inn, "industry": industry,
                        "registered_at": date(2023, 1, 1),
                        "director_name": director,
                    })
                    company_id = conn.scalar(text("""
                        SELECT id FROM alfa.companies WHERE inn = :inn
                    """), {"inn": inn})
                    effective_inn = inn
                    user_id = conn.scalar(text("""
                        INSERT INTO alfa.users
                            (email, password_hash, role, company_id, phone)
                        VALUES (:email, :password_hash, 'CLIENT', :company_id, :phone)
                        RETURNING id
                    """), {
                        "email": email,
                        "password_hash": hasher.hash(client_password),
                        "company_id": company_id,
                        "phone": phone,
                    })

                # Профиль, уже привязанный к исходной компании, не сбрасываем:
                # его могли вручную настроить для конкретного тестового кейса.
                conn.execute(text("""
                    INSERT INTO alfa.mock_profiles
                        (company_id, registry_flag, credit_history_flag)
                    VALUES (:company_id, :fns, :bki)
                    ON CONFLICT (company_id) DO NOTHING
                """), {"company_id": company_id, "fns": fns, "bki": bki})

                # Если 007 содержит внешний справочник — держим демоданные согласованными.
                exists = conn.scalar(text("SELECT to_regclass('alfa.demo_external_profiles')"))
                if exists is not None:
                    conn.execute(text("""
                        INSERT INTO alfa.demo_external_profiles
                            (inn, registry_flag, credit_history_flag)
                        VALUES (:inn, :fns, :bki)
                        ON CONFLICT (inn) DO NOTHING
                    """), {"inn": effective_inn, "fns": fns, "bki": bki})

                new_operations += _seed_missing_operations(
                    conn, company_id, user_id, code, effective_inn, index
                )

            bank = conn.execute(text("""
                SELECT role::text AS role, company_id
                FROM alfa.users WHERE email = 'bank@example.test'
            """)).mappings().first()
            if bank and (bank["role"] != "BANK_EMPLOYEE" or bank["company_id"] is not None):
                raise ValueError("Конфликт демоаккаунта bank@example.test")

            conn.execute(text("""
                INSERT INTO alfa.users (email, password_hash, role, company_id)
                VALUES ('bank@example.test', :hash, 'BANK_EMPLOYEE', NULL)
                ON CONFLICT (email) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    active = true
                WHERE alfa.users.role = 'BANK_EMPLOYEE'
                  AND alfa.users.company_id IS NULL
            """), {"hash": hasher.hash(bank_password)})

        print(f"Демоаккаунты подготовлены: {len(CLIENTS)} клиентов + 1 сотрудник банка.")
        print(f"Новых банковских операций добавлено: {new_operations}.")
        print("Email клиентов:")
        for code, *_ in CLIENTS:
            print(f"  {code}@example.test")
        print("Email сотрудника: bank@example.test")
        print("Пароли синхронизированы с .env, их значения не выводятся.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
