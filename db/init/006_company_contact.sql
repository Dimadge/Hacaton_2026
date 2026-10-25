-- Контакты компании: телефон пользователя и ФИО руководителя.
-- Применить один раз к существующей БД. Для новой БД файл лежит в db/init.
-- Старые учётки остаются с NULL: телефон и ФИО спрашиваются при новой регистрации.
BEGIN;
SET LOCAL TIME ZONE 'UTC';

ALTER TABLE alfa.users ADD COLUMN IF NOT EXISTS phone text
    CHECK (phone ~ '^\+[1-9][0-9]{7,14}$');

ALTER TABLE alfa.companies ADD COLUMN IF NOT EXISTS director_name text
    CHECK (director_name IS NULL OR length(btrim(director_name)) BETWEEN 1 AND 200);

COMMIT;
