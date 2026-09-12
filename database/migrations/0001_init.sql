-- 0001_init — initial schema.
-- SQLite: sqlite3 backend/data/tryon.db < database/migrations/0001_init.sql
-- (or simply run `python backend/scripts/init_db.py`, which is the supported path)
--
-- For PostgreSQL, swap the types:
--   INTEGER PRIMARY KEY AUTOINCREMENT -> GENERATED ALWAYS AS IDENTITY
--   JSON                              -> JSONB
--   BOOLEAN DEFAULT 1                 -> BOOLEAN DEFAULT TRUE
--   TIMESTAMP                         -> TIMESTAMPTZ
-- then set TRYON_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/tryon

.read ../schema.sql
