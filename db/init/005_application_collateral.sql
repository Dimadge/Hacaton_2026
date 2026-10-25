-- Альфа.Навигатор: залог по кредитной заявке. Только изменения БД.
-- Применить ОДИН раз к существующей БД после создания базовых таблиц 001.
-- Для новой БД положить в db/init рядом с 001–004.
-- Старые документы сохраняют collateral_id=NULL.
-- Не меняет кредитные решения, скоринг, API или интерфейс.
BEGIN;
SET LOCAL TIME ZONE 'UTC';

CREATE TABLE alfa.application_collateral (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES alfa.loan_applications(id),
    collateral_type text NOT NULL CHECK (collateral_type IN
        ('REAL_ESTATE', 'VEHICLE', 'EQUIPMENT', 'INVENTORY', 'OTHER')),
    description text NOT NULL CHECK (length(btrim(description)) BETWEEN 1 AND 4000),
    owner_name text NOT NULL CHECK (length(btrim(owner_name)) BETWEEN 1 AND 500),
    ownership_type text NOT NULL CHECK (ownership_type IN ('BORROWER', 'THIRD_PARTY')),
    declared_value alfa.money_rub NOT NULL CHECK (declared_value > 0),
    assessed_value alfa.money_rub,
    currency text NOT NULL DEFAULT 'RUB' CHECK (currency = 'RUB'),
    has_encumbrance boolean, -- NULL: сведений пока нет, false: заявлено отсутствие
    status text NOT NULL DEFAULT 'DECLARED'
        CHECK (status IN ('DECLARED', 'UNDER_REVIEW', 'ACCEPTED', 'REJECTED')),
    review_comment text CHECK (length(review_comment) <= 4000),
    reviewed_by uuid REFERENCES alfa.users(id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, application_id),
    -- Принятый залог должен иметь положительную оценку и известный флаг обременения.
    CHECK (status <> 'ACCEPTED' OR
        (assessed_value IS NOT NULL AND assessed_value > 0 AND has_encumbrance IS NOT NULL)),
    -- Итог проверки содержит автора, дату и объяснение.
    CHECK (status NOT IN ('ACCEPTED', 'REJECTED') OR
        (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
         AND review_comment IS NOT NULL AND length(btrim(review_comment)) > 0)),
    CHECK ((reviewed_by IS NULL) = (reviewed_at IS NULL))
);

CREATE INDEX collateral_application_idx ON alfa.application_collateral(application_id);
CREATE INDEX collateral_reviewer_idx ON alfa.application_collateral(reviewed_by);
CREATE INDEX collateral_review_queue_idx ON alfa.application_collateral(status, created_at);

CREATE FUNCTION alfa.guard_collateral_record() RETURNS trigger
LANGUAGE plpgsql SET search_path = alfa, pg_temp AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.id <> OLD.id OR NEW.application_id <> OLD.application_id THEN
            RAISE EXCEPTION 'Нельзя перенести залог в другую заявку или изменить его id';
        END IF;
        NEW.created_at := OLD.created_at;
    END IF;
    IF NEW.reviewed_by IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM alfa.users WHERE id = NEW.reviewed_by AND role = 'BANK_EMPLOYEE'
    ) THEN
        RAISE EXCEPTION 'Проверяющий залог должен иметь роль BANK_EMPLOYEE';
    END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
CREATE TRIGGER collateral_record_guard
BEFORE INSERT OR UPDATE ON alfa.application_collateral
FOR EACH ROW EXECUTE FUNCTION alfa.guard_collateral_record();

ALTER TABLE alfa.application_documents ADD COLUMN collateral_id uuid;
ALTER TABLE alfa.application_documents ADD CONSTRAINT document_collateral_same_application
    FOREIGN KEY (collateral_id, application_id)
    REFERENCES alfa.application_collateral(id, application_id);
CREATE INDEX documents_collateral_idx
    ON alfa.application_documents(collateral_id, application_id)
    WHERE collateral_id IS NOT NULL;

COMMENT ON TABLE alfa.application_collateral IS
    'Заявленные предметы залога. ACCEPTED — результат демо-проверки, не юридическое оформление.';
COMMENT ON COLUMN alfa.application_collateral.assessed_value IS
    'Стоимость после оценки; NULL до оценки. Не является автоматически кредитным лимитом.';
COMMENT ON COLUMN alfa.application_documents.collateral_id IS
    'Необязательная ссылка на предмет залога той же кредитной заявки.';

-- Техническая роль из согласованной конфигурации. Если её ещё нет, выдайте права
-- после создания: GRANT SELECT,INSERT,UPDATE ON alfa.application_collateral TO hacaton_app;
-- Имя другой runtime-роли замените вручную. DELETE здесь не выдаётся.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hacaton_app') THEN
        GRANT SELECT, INSERT, UPDATE ON alfa.application_collateral TO hacaton_app;
    END IF;
END;
$$;

-- Авторизация остаётся задачей backend: клиент не должен изменять оценку,
-- статус принятия, reviewed_by/reviewed_at. FK и триггер не заменяют проверку JWT.
-- Правила кредитования под залог, дисконты оценки и SMS здесь не реализуются.
COMMIT;
