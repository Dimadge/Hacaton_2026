-- Только изменения БД. Применить один раз после 001 и 002.
-- Старые данные сохраняются. Backend/frontend этой миграцией не меняются.
-- phone допускает NULL для совместимости со старыми пользователями и API.
-- Отрасль необязательна в БД; требование в форме/API нужно менять отдельно.
-- Импорт и правила принятия кредитных решений здесь не реализуются.
BEGIN;
ALTER TABLE alfa.users ADD COLUMN phone text CHECK(phone ~ '^\+[1-9][0-9]{7,14}$');
-- Старые учётки сохраняются с NULL; для новой регистрации телефон обязателен в API.
ALTER TABLE alfa.companies ALTER COLUMN industry DROP NOT NULL;
ALTER TABLE alfa.companies ALTER COLUMN industry SET DEFAULT 'UNKNOWN';
CREATE TABLE alfa.bank_accounts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 company_id uuid NOT NULL REFERENCES alfa.companies(id),
 external_id text NOT NULL UNIQUE CHECK(length(external_id) BETWEEN 1 AND 100),
 currency text NOT NULL DEFAULT 'RUB' CHECK(currency='RUB'),
 opened_at date NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bank_accounts_company ON alfa.bank_accounts(company_id);
CREATE TABLE alfa.bank_operations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 account_id uuid NOT NULL REFERENCES alfa.bank_accounts(id),
 external_id text NOT NULL CHECK(length(external_id) BETWEEN 1 AND 100),
 booked_at timestamptz NOT NULL,
 direction text NOT NULL CHECK(direction IN ('IN','OUT')),
 category text NOT NULL CHECK(category IN ('SALES','OPERATING','OWN_TRANSFER','LOAN','OTHER')),
 amount alfa.money_rub NOT NULL CHECK(amount>0),
 description text NOT NULL DEFAULT '' CHECK(length(description)<=1000),
 imported_by uuid NOT NULL REFERENCES alfa.users(id),
 imported_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(account_id,external_id)
);
CREATE INDEX bank_operations_time ON alfa.bank_operations(account_id,booked_at);
CREATE TRIGGER immutable_operations BEFORE UPDATE OR DELETE ON alfa.bank_operations
 FOR EACH ROW EXECUTE FUNCTION alfa.forbid_mutation();
CREATE TABLE alfa.bank_history_coverage (
 account_id uuid NOT NULL REFERENCES alfa.bank_accounts(id),
 month date NOT NULL CHECK(extract(day FROM month)=1),
 confirmed_by uuid NOT NULL REFERENCES alfa.users(id),
 confirmed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(account_id,month)
);
-- Наличие счета и наличие истории — два независимых признака.
CREATE VIEW alfa.company_bank_history_status AS
SELECT c.id AS company_id,
 EXISTS(SELECT 1 FROM alfa.bank_accounts a WHERE a.company_id=c.id) AS is_bank_customer,
 EXISTS(SELECT 1 FROM alfa.bank_accounts a JOIN alfa.bank_operations o ON o.account_id=a.id
        WHERE a.company_id=c.id) AS has_operations
FROM alfa.companies c;
COMMIT;
