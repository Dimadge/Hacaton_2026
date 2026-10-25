-- Demo one-time signing code. Apply after 001 base schema.
BEGIN;
CREATE TABLE IF NOT EXISTS alfa.signing_codes (
    application_id UUID PRIMARY KEY REFERENCES alfa.loan_applications(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    used_at TIMESTAMPTZ
);
COMMIT;
