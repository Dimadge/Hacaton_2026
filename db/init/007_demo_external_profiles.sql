
BEGIN;


CREATE TABLE IF NOT EXISTS alfa.demo_external_profiles (
    inn VARCHAR(12) PRIMARY KEY
        CHECK (inn ~ '^([0-9]{10}|[0-9]{12})$'),

    registry_flag TEXT NOT NULL
        CHECK (registry_flag IN (
            'active', 'inactive', 'mismatch', 'unknown'
        )),

    credit_history_flag TEXT NOT NULL
        CHECK (credit_history_flag IN (
            'good', 'minor_delay', 'critical', 'unknown'
        ))
);

INSERT INTO alfa.demo_external_profiles (
    inn,
    registry_flag,
    credit_history_flag
)
SELECT
    c.inn,
    mp.registry_flag,
    mp.credit_history_flag
FROM alfa.companies c
JOIN alfa.mock_profiles mp
    ON mp.company_id = c.id
ON CONFLICT (inn) DO NOTHING;


INSERT INTO alfa.demo_external_profiles (
    inn,
    registry_flag,
    credit_history_flag
)
VALUES (
    '9901234561',
    'active',
    'minor_delay'
)
ON CONFLICT (inn) DO NOTHING;


INSERT INTO alfa.mock_profiles (
    company_id,
    registry_flag,
    credit_history_flag
)
SELECT
    c.id,
    d.registry_flag,
    d.credit_history_flag
FROM alfa.companies c
JOIN alfa.demo_external_profiles d
    ON d.inn = c.inn
ON CONFLICT (company_id) DO NOTHING;

COMMIT;
