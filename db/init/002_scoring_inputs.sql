-- Дополнительные финансовые данные для скоринга.
BEGIN;

-- NULL = резерв не указан; 0 = указан нулевой резерв.
ALTER TABLE alfa.financial_profiles
ADD COLUMN cash_reserve alfa.money_rub;

-- Помесячные показатели конкретной версии анкеты.
CREATE TABLE alfa.monthly_financials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    financial_profile_id uuid NOT NULL
        REFERENCES alfa.financial_profiles(id),

    month date NOT NULL
        CHECK (EXTRACT(DAY FROM month) = 1),

    revenue alfa.money_rub NOT NULL,
    expenses alfa.money_rub NOT NULL,

    created_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (financial_profile_id, month)
);

-- Сохранённую историю нельзя переписывать или удалять.
CREATE TRIGGER immutable_months
BEFORE UPDATE OR DELETE ON alfa.monthly_financials
FOR EACH ROW
EXECUTE FUNCTION alfa.forbid_mutation();

CREATE TRIGGER immutable_months_truncate
BEFORE TRUNCATE ON alfa.monthly_financials
FOR EACH STATEMENT
EXECUTE FUNCTION alfa.forbid_mutation();

COMMIT;