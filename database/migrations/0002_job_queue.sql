-- 0002_job_queue — queued execution for Phase 2 engines (ADR-0001).
--
-- SQLite: sqlite3 backend/data/tryon.db < database/migrations/0002_job_queue.sql
--
-- Adds progress/cancellation state to tryon_results. `status` also gains a
-- 'cancelled' value.
--
-- No constraint change is needed for a database built by init_db.py: SQLAlchemy's
-- Enum defaults to create_constraint=False, so `status` is a plain VARCHAR there
-- and the new value just works. Only a database built from the hand-written
-- database/schema.sql carries the CHECK, and SQLite cannot ALTER one in place --
-- rebuild with `make clean && make db` if you are in that case.
--
-- PostgreSQL, if `status` was created as a native enum type:
--   ALTER TYPE resultstatus ADD VALUE IF NOT EXISTS 'cancelled';

ALTER TABLE tryon_results ADD COLUMN progress REAL NOT NULL DEFAULT 0.0;
ALTER TABLE tryon_results ADD COLUMN cancelled BOOLEAN NOT NULL DEFAULT 0;
