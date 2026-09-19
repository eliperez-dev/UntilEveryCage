-- Installed only by the disposable E2E Postgres image on first initialization.
-- The importer also checks current_database/current_user, so a copied marker
-- row cannot authorize a different database or role.
CREATE SCHEMA IF NOT EXISTS uec;
CREATE TABLE IF NOT EXISTS uec.disposable_import_guard (
    marker TEXT PRIMARY KEY,
    database_name TEXT NOT NULL,
    role_name TEXT NOT NULL
);
INSERT INTO uec.disposable_import_guard(marker, database_name, role_name)
VALUES ('uec-e2e-disposable-v1', 'uec', 'uec')
ON CONFLICT (marker) DO NOTHING;
