# database/

SQLite is the MVP store. The file lives at `backend/data/tryon.db` (git-ignored).

| File | Purpose |
| --- | --- |
| `schema.sql` | Human-readable reference schema, kept in sync with `backend/app/models.py` |
| `migrations/0001_init.sql` | Initial migration + Postgres type mapping notes |

## Create / reset

```bash
cd backend
python scripts/init_db.py        # create tables + sync assets/clothes
rm -f data/tryon.db*             # nuke and start over
```

Tables are created by SQLAlchemy `Base.metadata.create_all`. Once the schema
starts evolving, add Alembic:

```bash
pip install alembic
alembic init migrations
# point alembic.ini at TRYON_DATABASE_URL, target_metadata = app.database.Base.metadata
```

## Switching to PostgreSQL

```bash
docker compose up -d postgres
export TRYON_DATABASE_URL="postgresql+psycopg://tryon:tryon@localhost:5432/tryon"
pip install "psycopg[binary]"
python scripts/init_db.py
```

Nothing else changes — no raw SQL outside this folder.

## Table map

- `clothing_items` — catalog row per garment PNG, plus its overlay calibration
  (`anchor_type`, `scale_multiplier`, `pivot_x/y`, offsets).
- `tryon_sessions` — one webcam session; stores resolution and measured FPS.
- `tryon_results` — every generated image (Phase 1 snapshot or Phase 2 AI).
- `result_cache` — `(input_hash, engine)` → result, so repeats are free.
- `app_settings` — key/value mirror of the frontend settings panel.
