-- AI Virtual Try-On — reference schema (SQLite dialect, MVP).
-- The backend creates these tables automatically via SQLAlchemy
-- (`python scripts/init_db.py`). This file is the human-readable contract and
-- the starting point for a Postgres migration (see migrations/).

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Catalog: one row per garment file in assets/clothes/<category>/
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clothing_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    slug              VARCHAR(128) NOT NULL UNIQUE,
    name              VARCHAR(160) NOT NULL,
    category          VARCHAR(16)  NOT NULL
                      CHECK (category IN ('shirts','pants','jackets','hats','shoes','glasses')),

    file_path         VARCHAR(512) NOT NULL,   -- relative to assets/clothes/
    thumbnail_path    VARCHAR(512),
    natural_width     INTEGER,
    natural_height    INTEGER,

    brand             VARCHAR(120),
    color             VARCHAR(40),
    size              VARCHAR(20),
    tags              JSON NOT NULL DEFAULT '[]',
    description       TEXT,

    -- Phase 1 overlay calibration (see assets/clothes/catalog.json)
    anchor_type       VARCHAR(8) NOT NULL DEFAULT 'torso'
                      CHECK (anchor_type IN ('torso','hips','head','feet','eyes')),
    scale_multiplier  REAL NOT NULL DEFAULT 1.0,  -- PNG width / landmark span
    offset_x          REAL NOT NULL DEFAULT 0.0,  -- in units of landmark span
    offset_y          REAL NOT NULL DEFAULT 0.0,
    rotation_offset   REAL NOT NULL DEFAULT 0.0,  -- degrees
    pivot_x           REAL NOT NULL DEFAULT 0.5,  -- anchor inside PNG, 0..1
    pivot_y           REAL NOT NULL DEFAULT 0.08,
    opacity           REAL NOT NULL DEFAULT 1.0,
    z_index           INTEGER NOT NULL DEFAULT 10,

    is_active         BOOLEAN NOT NULL DEFAULT 1,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_clothing_items_category ON clothing_items (category);
CREATE INDEX IF NOT EXISTS ix_clothing_items_slug     ON clothing_items (slug);

-- ---------------------------------------------------------------------------
-- One row per webcam session opened by the frontend (FPS telemetry lives here)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tryon_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id        VARCHAR(36) NOT NULL UNIQUE,  -- uuid4, used by the API
    started_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at         TIMESTAMP,
    user_agent       VARCHAR(400),
    camera_label     VARCHAR(200),
    frame_width      INTEGER,
    frame_height     INTEGER,
    avg_fps          REAL,
    frames_processed INTEGER NOT NULL DEFAULT 0,
    notes            TEXT
);

-- ---------------------------------------------------------------------------
-- Generated try-on images (Phase 1 snapshots and Phase 2 AI results)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tryon_results (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id        VARCHAR(36) NOT NULL UNIQUE,
    session_id       INTEGER REFERENCES tryon_sessions(id) ON DELETE CASCADE,
    clothing_item_id INTEGER NOT NULL REFERENCES clothing_items(id) ON DELETE CASCADE,

    engine           VARCHAR(40) NOT NULL DEFAULT 'overlay',
    status           VARCHAR(12) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','processing','completed','failed','cancelled')),
    input_hash       VARCHAR(64) NOT NULL,   -- sha256(person + garment + params)
    person_path      VARCHAR(512),
    output_path      VARCHAR(512),           -- relative to backend/data/outputs/
    pose_landmarks   JSON,
    params           JSON NOT NULL DEFAULT '{}',
    latency_ms       INTEGER,
    error            TEXT,
    progress         REAL NOT NULL DEFAULT 0.0,   -- 0..1 while a queued engine runs
    cancelled        BOOLEAN NOT NULL DEFAULT 0,  -- cancel requested (ADR-0001)
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_tryon_results_item   ON tryon_results (clothing_item_id);
CREATE INDEX IF NOT EXISTS ix_tryon_results_hash   ON tryon_results (input_hash);
CREATE INDEX IF NOT EXISTS ix_tryon_results_status ON tryon_results (status);
CREATE INDEX IF NOT EXISTS ix_tryon_results_engine ON tryon_results (engine);

-- ---------------------------------------------------------------------------
-- Cache: identical (input_hash, engine) never re-runs an expensive model
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS result_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    input_hash  VARCHAR(64) NOT NULL,
    engine      VARCHAR(40) NOT NULL,
    result_id   INTEGER NOT NULL REFERENCES tryon_results(id) ON DELETE CASCADE,
    hit_count   INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_hit_at TIMESTAMP,
    CONSTRAINT uq_result_cache_hash_engine UNIQUE (input_hash, engine)
);

CREATE INDEX IF NOT EXISTS ix_result_cache_lookup ON result_cache (input_hash, engine);

-- ---------------------------------------------------------------------------
-- User preferences mirroring the frontend settings panel
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    key        VARCHAR(64) PRIMARY KEY,
    value      JSON,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
