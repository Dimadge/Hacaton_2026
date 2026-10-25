BEGIN;

INSERT INTO alfa.reason_codes (
    code,
    client_message
)
VALUES (
    'COLLATERAL_LIMIT',
    'Для запрошенной суммы недостаточно принятого залогового обеспечения.'
)
ON CONFLICT (code) DO NOTHING;

COMMIT;
