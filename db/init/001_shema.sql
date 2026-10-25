BEGIN;

SET LOCAL TIME ZONE 'UTC';

CREATE SCHEMA IF NOT EXISTS alfa;

SET LOCAL search_path = alfa, public;

CREATE DOMAIN money_rub AS numeric(18,2)
 CHECK (VALUE >= 0 AND VALUE < 'Infinity'::numeric);
CREATE DOMAIN annual_rate AS numeric(9,6)
 CHECK (VALUE >= 0 AND VALUE <= 1);
CREATE TYPE user_role AS ENUM ('CLIENT','BANK_EMPLOYEE');
CREATE TYPE application_status AS ENUM
 ('DRAFT','SUBMITTED','CHECKING','NEED_INFO','UNDER_REVIEW','OFFERED',
  'ACCEPTED','SIGNED','DISBURSED','REJECTED','CANCELLED');
CREATE TYPE decision_kind AS ENUM
 ('APPROVE','COUNTER_OFFER','MANUAL_REVIEW','REQUEST_INFO','REJECT');
CREATE TYPE risk_kind AS ENUM ('LOW','MEDIUM','HIGH');

CREATE TABLE companies (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL CHECK (btrim(name) <> ''),
 inn varchar(12) NOT NULL UNIQUE CHECK (inn ~ '^([0-9]{10}|[0-9]{12})$'),
 industry text NOT NULL CHECK (btrim(industry) <> ''),
 registered_at date NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 email text NOT NULL CHECK (email = lower(btrim(email)) AND position('@' in email)>1),
 password_hash text NOT NULL CHECK (length(password_hash)>=40),
 role user_role NOT NULL,
 company_id uuid REFERENCES companies(id),
 active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(email),
 CHECK ((role='CLIENT' AND company_id IS NOT NULL) OR
        (role='BANK_EMPLOYEE' AND company_id IS NULL))
);
CREATE INDEX users_company_idx ON users(company_id);

CREATE TABLE credit_products (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 code text NOT NULL UNIQUE,
 name text NOT NULL,
 min_amount money_rub NOT NULL CHECK (min_amount>0),
 max_amount money_rub NOT NULL,
 min_term integer NOT NULL CHECK (min_term>0),
 max_term integer NOT NULL,
 demo_rate annual_rate NOT NULL,
 active boolean NOT NULL DEFAULT true,
 CHECK (max_amount>=min_amount), CHECK (max_term>=min_term)
);
INSERT INTO credit_products(code,name,min_amount,max_amount,min_term,max_term,demo_rate) VALUES
 ('WORKING_CAPITAL','Оборотный',200000,3000000,6,24,0.20),
 ('INVESTMENT','Инвестиционный',500000,5000000,12,60,0.18);

CREATE TABLE scoring_rules (
 rule_version text PRIMARY KEY,
 parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters)='object'),
 description text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO scoring_rules VALUES ('rules-v1',
 '{"payment_share":0.40,"weights":[0.25,0.20,0.40,0.15],"low_min":75,"medium_min":50,"amount_step":10000,"max_offers":3}',
 'Учебный индекс, не вероятность одобрения. Формулы — раздел 6.6; расчёт в Python Decimal.',now());
CREATE TABLE reason_codes (
 code text PRIMARY KEY,
 client_message text NOT NULL
);
INSERT INTO reason_codes VALUES
 ('PAYMENT_OVER_LIMIT','Запрошенные условия создают слишком высокую нагрузку.'),
 ('CASHFLOW_NONPOSITIVE','Недостаточно операционного денежного потока.'),
 ('CREDIT_HISTORY_DELAY','Нужна дополнительная проверка кредитной истории.'),
 ('CREDIT_HISTORY_CRITICAL','Критический фактор кредитной истории.'),
 ('REGISTRY_INACTIVE','Организация неактивна по данным mock ФНС.'),
 ('REGISTRY_MISMATCH','Требуется ручная проверка сведений организации.'),
 ('MISSING_FINANCIAL_DATA','Заполните обязательные финансовые сведения.'),
 ('PRODUCT_LIMIT','Сумма или срок не соответствуют продукту.'),
 ('ALTERNATIVE_AVAILABLE','Рассчитаны альтернативные условия.'),
 ('DOCS_MISSING','Добавьте подтверждающий документ или сведения.'),
 ('RISK_HIGH','Высокий риск по учебной модели.'),
 ('RISK_MEDIUM','Требуется ручная оценка риска.'),
 ('UNKNOWN_VERIFICATION','Неизвестный результат проверки: нужна ручная обработка.');

CREATE TABLE loan_applications (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 company_id uuid NOT NULL REFERENCES companies(id),
 created_by uuid NOT NULL REFERENCES users(id),
 product_id uuid NOT NULL REFERENCES credit_products(id),
 amount money_rub NOT NULL CHECK (amount>0),
 term integer NOT NULL CHECK (term>0),
 purpose text NOT NULL CHECK (btrim(purpose)<>''),
 status application_status NOT NULL DEFAULT 'DRAFT',
 version integer NOT NULL DEFAULT 1 CHECK (version>0),
 accepted_offer_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((status IN ('ACCEPTED','SIGNED','DISBURSED')) = (accepted_offer_id IS NOT NULL))
);
CREATE INDEX applications_company_idx ON loan_applications(company_id,created_at DESC);
CREATE INDEX applications_queue_idx ON loan_applications(status,updated_at);
CREATE INDEX applications_product_idx ON loan_applications(product_id);
CREATE INDEX applications_creator_idx ON loan_applications(created_by);

-- Анкеты версионируются вставкой новой строки. Старые снимки не переписываются.
CREATE TABLE financial_profiles (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 application_id uuid NOT NULL REFERENCES loan_applications(id),
 revision integer NOT NULL CHECK (revision>0),
 revenue money_rub NOT NULL,
 expenses money_rub NOT NULL,
 debt_payments money_rub NOT NULL,
 age_months integer NOT NULL CHECK (age_months>=0),
 document_confirmed boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(application_id,revision), UNIQUE(id,application_id)
);
CREATE TABLE application_documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 application_id uuid NOT NULL REFERENCES loan_applications(id),
 uploaded_by uuid NOT NULL REFERENCES users(id),
 file_name text NOT NULL,
 storage_key text NOT NULL UNIQUE,
 mime_type text NOT NULL,
 size_bytes bigint NOT NULL CHECK (size_bytes>=0),
 sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_application_idx ON application_documents(application_id);
CREATE INDEX documents_uploader_idx ON application_documents(uploaded_by);

CREATE TABLE mock_profiles (
 company_id uuid PRIMARY KEY REFERENCES companies(id),
 registry_flag text NOT NULL CHECK (registry_flag IN ('active','inactive','mismatch','unknown')),
 credit_history_flag text NOT NULL CHECK (credit_history_flag IN ('good','minor_delay','critical','unknown')),
 updated_at timestamptz NOT NULL DEFAULT now()
);
-- Каждая повторная подача создаёт новый цикл с неизменяемыми входными данными.
CREATE TABLE evaluation_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 application_id uuid NOT NULL REFERENCES loan_applications(id),
 financial_profile_id uuid NOT NULL,
 submission_version integer NOT NULL CHECK (submission_version>0),
 rule_version text NOT NULL REFERENCES scoring_rules(rule_version),
 input_snapshot jsonb NOT NULL CHECK (jsonb_typeof(input_snapshot)='object'),
 product_snapshot jsonb NOT NULL CHECK (jsonb_typeof(product_snapshot)='object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(application_id,submission_version), UNIQUE(id,application_id),
 FOREIGN KEY(financial_profile_id,application_id)
  REFERENCES financial_profiles(id,application_id)
);
CREATE INDEX runs_profile_idx ON evaluation_runs(financial_profile_id,application_id);
CREATE INDEX runs_rules_idx ON evaluation_runs(rule_version);
CREATE TABLE verifications (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 application_id uuid NOT NULL,
 run_id uuid NOT NULL,
 source text NOT NULL CHECK (source IN ('FNS','BKI')),
 result text NOT NULL,
 payload jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(payload)='object'),
 checked_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,source),
 FOREIGN KEY(run_id,application_id) REFERENCES evaluation_runs(id,application_id),
 CHECK ((source='FNS' AND result IN ('active','inactive','mismatch','unknown')) OR
        (source='BKI' AND result IN ('good','minor_delay','critical','unknown')))
);
CREATE INDEX verifications_app_idx ON verifications(application_id);
CREATE TABLE scoring_results (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 application_id uuid NOT NULL,
 run_id uuid NOT NULL UNIQUE,
 score integer NOT NULL CHECK (score BETWEEN 0 AND 100),
 score_raw numeric(8,5) NOT NULL CHECK (score_raw BETWEEN 0 AND 100),
 risk risk_kind NOT NULL,
 max_new_payment money_rub NOT NULL,
 cash_flow numeric(18,2) NOT NULL CHECK (abs(cash_flow)<'Infinity'::numeric),
 requested_payment money_rub NOT NULL,
 factors jsonb NOT NULL CHECK (jsonb_typeof(factors)='object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(run_id,application_id) REFERENCES evaluation_runs(id,application_id),
 CHECK ((score>=75 AND risk='LOW') OR (score>=50 AND score<75 AND risk='MEDIUM') OR
        (score<50 AND risk='HIGH'))
);
CREATE INDEX scoring_app_idx ON scoring_results(application_id);
CREATE TABLE scoring_result_reasons (
 scoring_result_id uuid NOT NULL REFERENCES scoring_results(id),
 reason_code text NOT NULL REFERENCES reason_codes(code),
 PRIMARY KEY(scoring_result_id,reason_code)
);
CREATE TABLE credit_decisions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 application_id uuid NOT NULL,
 run_id uuid NOT NULL,
 sequence_no integer NOT NULL CHECK (sequence_no>0),
 decision_type decision_kind NOT NULL,
 created_by uuid REFERENCES users(id),
 comment text,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(run_id,sequence_no), UNIQUE(id,application_id),
 FOREIGN KEY(run_id,application_id) REFERENCES evaluation_runs(id,application_id)
);
CREATE UNIQUE INDEX one_auto_decision_per_run ON credit_decisions(run_id) WHERE created_by IS NULL;
CREATE INDEX decisions_app_idx ON credit_decisions(application_id,created_at DESC);
CREATE INDEX decisions_actor_idx ON credit_decisions(created_by);
CREATE TABLE decision_reasons (
 decision_id uuid NOT NULL REFERENCES credit_decisions(id),
 reason_code text NOT NULL REFERENCES reason_codes(code),
 PRIMARY KEY(decision_id,reason_code)
);
CREATE TABLE credit_offers (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 application_id uuid NOT NULL,
 decision_id uuid NOT NULL,
 amount money_rub NOT NULL CHECK (amount>0),
 term integer NOT NULL CHECK (term>0),
 rate annual_rate NOT NULL,
 monthly_payment money_rub NOT NULL CHECK (monthly_payment>0),
 rank integer NOT NULL CHECK (rank BETWEEN 1 AND 3),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(id,application_id), UNIQUE(decision_id,rank),
 UNIQUE(decision_id,amount,term,rate),
 FOREIGN KEY(decision_id,application_id) REFERENCES credit_decisions(id,application_id)
);
CREATE INDEX offers_app_idx ON credit_offers(application_id);
ALTER TABLE loan_applications ADD CONSTRAINT accepted_offer_belongs_to_application
 FOREIGN KEY(accepted_offer_id,id) REFERENCES credit_offers(id,application_id);
CREATE VIEW credit_offers_with_acceptance AS
 SELECT o.*, (a.accepted_offer_id IS NOT DISTINCT FROM o.id) AS accepted
 FROM credit_offers o JOIN loan_applications a ON a.id=o.application_id;
CREATE VIEW scoring_results_with_rules AS
 SELECT s.*, r.rule_version FROM scoring_results s JOIN evaluation_runs r ON r.id=s.run_id;

CREATE TABLE application_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 application_id uuid NOT NULL REFERENCES loan_applications(id),
 actor_id uuid REFERENCES users(id),
 action text NOT NULL,
 from_status application_status,
 to_status application_status NOT NULL,
 application_version integer NOT NULL CHECK (application_version>0),
 at timestamptz NOT NULL DEFAULT clock_timestamp(),
 metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata)='object'),
 UNIQUE(application_id,application_version)
);
CREATE INDEX events_actor_idx ON application_events(actor_id);
CREATE TABLE news_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 title text NOT NULL CHECK (btrim(title)<>''),
 body text NOT NULL,
 industry_tags text[] NOT NULL DEFAULT '{}',
 active boolean NOT NULL DEFAULT true,
 published_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX news_tags_idx ON news_items USING gin(industry_tags);
CREATE INDEX news_feed_idx ON news_items(published_at DESC) WHERE active;
INSERT INTO news_items(title,body,industry_tags) VALUES
 ('Оборотное финансирование','Демо-новость для торговли.',ARRAY['TRADE']),
 ('Обновление оборудования','Демо-новость для производства.',ARRAY['MANUFACTURING']),
 ('Как читать условия кредита','Учебная новость для всех отраслей.','{}');

CREATE TABLE idempotency_keys (
 user_id uuid NOT NULL REFERENCES users(id),
 operation text NOT NULL CHECK (btrim(operation)<>''),
 key text NOT NULL CHECK (length(key) BETWEEN 1 AND 200),
 request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
 application_id uuid REFERENCES loan_applications(id),
 response_code integer CHECK (response_code BETWEEN 100 AND 599),
 response_body jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz,
 PRIMARY KEY(user_id,operation,key),
 CHECK ((completed_at IS NULL AND response_code IS NULL AND response_body IS NULL) OR
        (completed_at IS NOT NULL AND response_code IS NOT NULL AND response_body IS NOT NULL))
);
CREATE INDEX idempotency_app_idx ON idempotency_keys(application_id);

CREATE TABLE allowed_transitions (
 from_status application_status NOT NULL,
 to_status application_status NOT NULL,
 PRIMARY KEY(from_status,to_status)
);
INSERT INTO allowed_transitions VALUES
 ('DRAFT','SUBMITTED'),('SUBMITTED','CHECKING'),
 ('CHECKING','NEED_INFO'),('CHECKING','UNDER_REVIEW'),('CHECKING','OFFERED'),('CHECKING','REJECTED'),
 ('NEED_INFO','CHECKING'),
 ('UNDER_REVIEW','NEED_INFO'),('UNDER_REVIEW','OFFERED'),('UNDER_REVIEW','REJECTED'),
 ('OFFERED','ACCEPTED'),('OFFERED','CANCELLED'),
 ('ACCEPTED','SIGNED'),('SIGNED','DISBURSED');

CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Историческая запись % неизменяема', TG_TABLE_NAME; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['application_events','financial_profiles','evaluation_runs',
  'verifications','scoring_results','scoring_result_reasons','credit_decisions',
  'decision_reasons','credit_offers','scoring_rules'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON alfa.%I FOR EACH ROW EXECUTE FUNCTION alfa.forbid_mutation()',t);
  EXECUTE format('CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON alfa.%I FOR EACH STATEMENT EXECUTE FUNCTION alfa.forbid_mutation()',t);
 END LOOP;
END $$;

CREATE FUNCTION guard_application() RETURNS trigger LANGUAGE plpgsql
 SET search_path=alfa,pg_temp AS $$
DECLARE p credit_products; chosen credit_offers; latest uuid;
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.status<>'DRAFT' OR NEW.version<>1 THEN RAISE EXCEPTION 'Новая заявка должна быть DRAFT, version=1'; END IF;
 ELSE
  IF NEW.company_id<>OLD.company_id OR NEW.created_by<>OLD.created_by OR NEW.id<>OLD.id THEN
   RAISE EXCEPTION 'Владелец и идентификатор заявки неизменяемы';
  END IF;
  IF NEW.version<>OLD.version THEN RAISE EXCEPTION 'version увеличивается триггером'; END IF;
  IF ROW(NEW.product_id,NEW.amount,NEW.term,NEW.purpose) IS DISTINCT FROM
     ROW(OLD.product_id,OLD.amount,OLD.term,OLD.purpose) AND
     (OLD.status NOT IN ('DRAFT','NEED_INFO') OR NEW.status<>OLD.status) THEN
   RAISE EXCEPTION 'Редактирование разрешено только отдельно от подачи, в DRAFT/NEED_INFO';
  END IF;
  IF NEW.status<>OLD.status AND NOT EXISTS
    (SELECT 1 FROM allowed_transitions WHERE from_status=OLD.status AND to_status=NEW.status) THEN
   RAISE EXCEPTION 'Недопустимый переход % -> %',OLD.status,NEW.status;
  END IF;
  IF NEW.accepted_offer_id IS DISTINCT FROM OLD.accepted_offer_id AND
     NOT (OLD.status='OFFERED' AND NEW.status='ACCEPTED') THEN
   RAISE EXCEPTION 'Выбор оффера разрешён только при OFFERED -> ACCEPTED';
  END IF;
  IF NEW.status='ACCEPTED' AND OLD.status='OFFERED' THEN
   SELECT * INTO chosen FROM credit_offers WHERE id=NEW.accepted_offer_id AND application_id=NEW.id;
   SELECT id INTO latest FROM credit_decisions WHERE application_id=NEW.id ORDER BY created_at DESC,sequence_no DESC LIMIT 1;
   IF chosen.id IS NULL OR chosen.decision_id IS DISTINCT FROM latest THEN
    RAISE EXCEPTION 'Оффер отсутствует, принадлежит другой заявке или устарел';
   END IF;
  END IF;
  NEW.version:=OLD.version+1;
 END IF;
 IF TG_OP='INSERT' OR NEW.status IN ('DRAFT','NEED_INFO') THEN
  SELECT * INTO p FROM credit_products WHERE id=NEW.product_id;
  IF p.id IS NULL OR NOT p.active OR NEW.amount NOT BETWEEN p.min_amount AND p.max_amount OR
    NEW.term NOT BETWEEN p.min_term AND p.max_term THEN RAISE EXCEPTION 'Неверные параметры продукта'; END IF;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.created_by AND role='CLIENT' AND company_id=NEW.company_id) THEN
  RAISE EXCEPTION 'Создатель должен быть клиентом компании';
 END IF;
 NEW.updated_at:=clock_timestamp(); RETURN NEW;
END $$;
CREATE TRIGGER application_guard BEFORE INSERT OR UPDATE ON loan_applications
 FOR EACH ROW EXECUTE FUNCTION guard_application();
CREATE FUNCTION log_application() RETURNS trigger LANGUAGE plpgsql
 SET search_path=alfa,pg_temp AS $$
BEGIN
 INSERT INTO application_events(application_id,actor_id,action,from_status,to_status,application_version)
 VALUES(NEW.id,NULLIF(current_setting('app.actor_id',true),'')::uuid,
 CASE WHEN TG_OP='INSERT' THEN 'CREATE' WHEN NEW.status<>OLD.status THEN 'STATUS_CHANGE' ELSE 'UPDATE' END,
 CASE WHEN TG_OP='INSERT' THEN NULL ELSE OLD.status END,NEW.status,NEW.version);
 RETURN NEW;
END $$;
CREATE TRIGGER application_audit AFTER INSERT OR UPDATE ON loan_applications
 FOR EACH ROW EXECUTE FUNCTION log_application();

CREATE FUNCTION guard_offer() RETURNS trigger LANGUAGE plpgsql SET search_path=alfa,pg_temp AS $$
DECLARE d credit_decisions; p jsonb; lim numeric; expected numeric; r numeric;
BEGIN
 SELECT * INTO d FROM credit_decisions WHERE id=NEW.decision_id AND application_id=NEW.application_id;
 IF d.id IS NULL OR d.decision_type NOT IN ('APPROVE','COUNTER_OFFER') THEN RAISE EXCEPTION 'Решение не допускает оффер'; END IF;
 SELECT product_snapshot INTO p FROM evaluation_runs WHERE id=d.run_id;
 IF NOT (p ?& ARRAY['min_amount','max_amount','min_term','max_term','demo_rate']) THEN
  RAISE EXCEPTION 'Неполный снимок тарифа'; END IF;
 IF (NEW.amount BETWEEN (p->>'min_amount')::numeric AND (p->>'max_amount')::numeric
     AND NEW.term BETWEEN (p->>'min_term')::integer AND (p->>'max_term')::integer
     AND NEW.rate=(p->>'demo_rate')::numeric) IS DISTINCT FROM true THEN
  RAISE EXCEPTION 'Оффер нарушает тариф'; END IF;
 SELECT max_new_payment INTO lim FROM scoring_results WHERE run_id=d.run_id;
 IF lim IS NULL OR NEW.monthly_payment>lim THEN RAISE EXCEPTION 'Нет скоринга либо превышен лимит платежа'; END IF;
 r:=NEW.rate/12;
 expected:=CASE WHEN r=0 THEN NEW.amount/NEW.term ELSE NEW.amount*r/(1-power(1+r,-NEW.term)) END;
 IF NEW.monthly_payment<>round(expected,2) THEN RAISE EXCEPTION 'Неверный аннуитетный платёж'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER offer_guard BEFORE INSERT ON credit_offers FOR EACH ROW EXECUTE FUNCTION guard_offer();

COMMIT;
