# AI Virtual Try-On

A local desktop web app: your webcam feed, live MediaPipe pose tracking, and clothing
from a folder on your disk composited onto your body in real time.

Phase 1 (landmark-anchored PNG overlays, 30+ FPS) is **complete and running**. Phase 2
(IDM-VTON / CatVTON) has its engine interface, registry, cache and API surface already
wired — only the model weights and inference code are missing.

```
┌──────────────┐        ┌─────────────────────────────┐        ┌──────────────┐
│  Wardrobe    │        │        Camera stage         │        │  Settings    │
│  catalog     │        │  <video> + <canvas> overlay │        │  fit/engine  │
│  from disk   │        │  MediaPipe Pose in-browser  │        │  diagnostics │
└──────────────┘        └─────────────────────────────┘        └──────────────┘
        │                             │                                │
        └────────────── Next.js rewrites (same origin) ────────────────┘
                                      │
                            FastAPI · SQLite · Pillow
                      overlay engine ─ cache ─ catalog sync
```

---

## 1. Requirements

| | Version | Notes |
|---|---|---|
| Python | 3.11 – 3.14 | `requirements.txt` uses lower bounds, not hard pins, so new CPython releases work |
| Node.js | 20+ | 22 recommended |
| Browser | Chrome / Edge / Safari 17+ | Needs WebGL2 for the GPU delegate; falls back to CPU |
| Webcam | any | `getUserMedia` requires a secure context — `localhost` counts |

No GPU is required for Phase 1. Pose inference runs in the browser via WASM.

## 2. Installation

```bash
git clone <this repo> "AI Virtual Try-On" && cd "AI Virtual Try-On"
make setup
```

`make setup` runs four steps; run them by hand if you prefer:

```bash
# 1. Python environment
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt

# 2. Generate the 14 placeholder garments into assets/clothes/
backend/.venv/bin/python backend/scripts/generate_sample_clothes.py

# 3. Create tables and sync the catalog folder into the DB
backend/.venv/bin/python backend/scripts/init_db.py

# 4. Node deps. postinstall vendors the MediaPipe WASM + .task models
#    into frontend/public so the app runs offline.
cd frontend && npm install
```

Then start both processes:

```bash
make dev          # or two terminals:
make backend      #   http://127.0.0.1:8000  (docs at /docs)
make frontend     #   http://localhost:3000
```

Open **http://localhost:3000** and click *Enable camera*.

### Configuration

Copy `.env.example` to `.env` in the repo root. Every key is prefixed `TRYON_`:

| Key | Default | Purpose |
|---|---|---|
| `TRYON_DATABASE_URL` | `sqlite:///backend/data/tryon.db` | Point at Postgres to switch |
| `TRYON_DEFAULT_ENGINE` | `overlay` | `overlay` \| `catvton` \| `idm-vton` |
| `TRYON_CLOTHES_DIR` | `assets/clothes` | Catalog source of truth |
| `TRYON_OUTPUT_DIR` | `backend/data/outputs` | Generated try-on PNGs |
| `TRYON_MODELS_DIR` | `models/` | Phase 2 weights |
| `TRYON_CACHE_ENABLED` | `true` | Content-hash result cache |
| `TRYON_MAX_UPLOAD_MB` | `12` | Rejects oversized frames |

The frontend only needs `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`), used by
the Next rewrites — see `frontend/.env.local.example`.

### Docker

```bash
docker compose up --build     # http://localhost:3000
```

Reach it at `localhost`, not a LAN IP: browsers refuse `getUserMedia` on plain HTTP from
a non-local origin. Postgres is an opt-in profile:

```bash
docker compose --profile postgres up -d postgres
# then set TRYON_DATABASE_URL=postgresql+psycopg://tryon:tryon@postgres:5432/tryon
```

### Tests

```bash
make test     # 15 backend tests (pytest) + frontend tsc --noEmit
```

---

## 3. Project structure

```
assets/clothes/          Garment PNGs — the catalog source of truth
  catalog.json           Per-item calibration (anchor, scale, pivot, offsets)
  shirts/ jackets/ pants/ hats/ glasses/ shoes/
backend/
  app/
    config.py            Settings (TRYON_* env), path resolution
    database.py          Engine + session factory
    models.py            SQLAlchemy tables
    schemas.py           Pydantic request/response models
    routers/             health, clothing, sessions, tryon, settings
    services/
      catalog.py         Folder <-> DB reconciliation, thumbnails
      images.py          Decode/encode helpers, size guards
      tryon_service.py   Hash, cache lookup, engine dispatch, persistence
    tryon/
      base.py            TryOnEngine ABC — the Phase 2 plug point
      registry.py        name -> engine instance
      overlay_engine.py  Phase 1 geometry (twin of frontend/src/lib/anchors.ts)
      catvton_engine.py  Phase 2 stub (reports available=false)
      idm_vton_engine.py Phase 2 stub
  scripts/               generate_sample_clothes.py, init_db.py
  tests/                 conftest.py (tempdir DB) + test_api.py
database/
  schema.sql             Reference DDL
  migrations/0001_init.sql
frontend/
  src/app/               App Router entry, globals.css
  src/components/        TopBar, ClothingSidebar, CameraStage, SettingsPanel, ui
  src/hooks/             useWebcam, usePoseOverlay (the render loop)
  src/lib/               pose, anchors, draw, smoothing, api, types
  src/store/             useWardrobe, useSettings (zustand)
  public/mediapipe/      Vendored WASM
  public/models/         Vendored pose_landmarker_{lite,full,heavy}.task
models/                  Phase 2 VTON weights (gitignored)
```

## 4. Database schema

SQLite by default, Postgres-compatible. Full DDL in `database/schema.sql`.

- **clothing_items** — catalog row *plus its overlay calibration*: `anchor_type`
  (`torso`/`hips`/`head`/`eyes`/`feet`), `scale_multiplier`, `offset_x`, `offset_y`,
  `rotation_offset`, `pivot_x`, `pivot_y`, `opacity`, `z_index`. Keeping calibration on
  the garment means new art is a folder drop plus a `catalog.json` entry — no code change.
- **tryon_sessions** — one per camera session; FPS and frame-count telemetry.
- **tryon_results** — `public_id`, engine, status, `input_hash`, `output_path`,
  the pose landmarks used, params, `latency_ms`.
- **result_cache** — unique `(input_hash, engine)` with `hit_count`.
- **app_settings** — key/JSON-value, so the settings panel survives a browser reset.

## 5. API

Base `http://127.0.0.1:8000`. Interactive docs at `/docs`.

| Method | Path | |
|---|---|---|
| GET | `/api/health` | version, DB backend, catalog count |
| GET · POST | `/api/clothing` | list (filter by category/search) · create |
| GET | `/api/clothing/categories` | categories with counts |
| POST | `/api/clothing/sync` | rescan `assets/clothes/` |
| GET · PATCH · DELETE | `/api/clothing/{id}` | incl. live calibration tweaks |
| POST · GET | `/api/sessions` | start · list |
| GET · PATCH | `/api/sessions/{public_id}` | fetch · push FPS telemetry |
| GET | `/api/tryon/engines` | engines + `available` and `execution` |
| POST | `/api/tryon` | frame + garment -> `200` image (inline) or `202` job (queued) |
| GET | `/api/tryon/queue` | depth of the inference queue |
| GET | `/api/tryon/results` | history |
| GET · DELETE | `/api/tryon/cache` | stats · clear |
| GET | `/api/tryon/{public_id}` | result metadata — the poll target |
| POST | `/api/tryon/{public_id}/cancel` | drop a queued job |
| GET | `/api/tryon/{public_id}/image` | the PNG |
| GET · PUT · DELETE | `/api/settings` | persisted UI settings |

Static: `/assets/clothes/**` (garments + `.thumbs/`), `/outputs/**` (results).

## 6. How the overlay works

Every frame, `usePoseOverlay` does: `detectForVideo` → One Euro smoothing →
`effectiveOverlay` (garment calibration × user fit sliders) → `solvePlacements` →
`drawGarment` → `drawSkeleton`.

Two things are worth knowing before you touch the geometry:

**Rotation comes from the body axis, not from landmark order.** For a torso garment the
up-vector is `shoulder_midpoint − hip_midpoint`; hips use hips→knees, head uses
ears→shoulders, feet use the per-foot ankle→toe vector rotated 90°. Deriving the angle
from, say, `atan2(right_shoulder − left_shoulder)` bakes in an assumption about which
landmark is on which side of the screen, and inverts the moment the feed is mirrored.
The axis approach renders identically mirrored or not.

Glasses are the one exception, and they prove the rule. A frame sitting two degrees
off is obvious, so the `eyes` anchor takes its roll from the eye line itself. But an
eye line is an *undirected* axis — its perpendicular has two candidates, and choosing
between them by landmark order would flip the glasses upside down in a selfie feed.
So the solver picks the perpendicular pointing away from the shoulders, which is
mirror-invariant. `test_eyes_anchor_is_mirror_equivariant` pins that down.

**Shoes mirror, they don't rotate.** A left shoe is a reflected right shoe, so
`Placement` carries a `mirror` flag; the pivot is mirrored too (`1 − pivot_x`).

Scale is a reference landmark distance in pixels — shoulder span, hip span, ear span,
outer-eye span, ankle→toe length — times the garment's `scale_multiplier`. Step toward the camera and the
shirt grows with you.

`backend/app/tryon/overlay_engine.py` and `frontend/src/lib/anchors.ts` are deliberate
twins: same math, one in Pillow, one in Canvas 2D, so a server-rendered try-on matches
the live preview pixel for pixel. **Change one, change the other.**

## 7. Adding your own clothes

1. Drop a transparent PNG into `assets/clothes/<category>/`.
2. Add an entry to `assets/clothes/catalog.json` (or skip it and accept the
   per-category defaults).
3. Click **Sync** in the wardrobe panel, or `POST /api/clothing/sync`.

Shoot the garment flat, front-on, tightly cropped, garment pointing up. `pivot_x` /
`pivot_y` are the fraction of the image that should sit on the anchor point — for a
t-shirt, the middle of the collar, roughly `0.5, 0.08`.

---

## 8. Development roadmap

### Phase 1 — Real-time overlay ✅ shipped

- [x] Webcam capture with device picker, permission and hot-plug handling
- [x] MediaPipe Pose Landmarker in-browser (lite/full/heavy, GPU delegate + CPU fallback)
- [x] Skeleton and landmark overlay, toggleable
- [x] Catalog loaded from `assets/clothes/`, reconciled into the DB
- [x] Landmark-anchored compositing for shirts, then jackets, pants, hats, glasses, shoes
- [x] Scale from shoulder width / body size; One Euro smoothing
- [x] 30+ FPS on the `lite` model with the GPU delegate
- [x] Snapshot capture and PNG save
- [x] Server-side overlay engine producing identical output
- [x] Fit sliders, engine picker, cache stats, diagnostics
- [x] SQLite schema, FastAPI endpoints, Docker, tests

### Phase 2 — AI try-on (next)

The seams are already cut. `TryOnEngine` in `backend/app/tryon/base.py` defines
`is_available()`, `warmup()`, `cache_key_parts()` and the abstract `generate()`;
`registry.py` maps names to instances;
`tryon_service.py` hashes, caches and persists whatever comes back. The stubs return
`503` with an explanatory message until weights land.

1. **Vendor a model.** CatVTON first — ~800M params, far lighter than IDM-VTON, runs in
   ~8 GB VRAM. Weights go in `models/catvton/`.
2. **Implement `CatVTONEngine.generate()`.** Person image + garment image + a garment-region
   mask in, RGB out. The pose landmarks the frontend already ships with every request
   give you the mask for free — no separate human-parsing model needed for a first pass.
   Write `result.progress` from the pipeline's step callback and check `result.cancelled`
   there to make cancellation interrupt a running job rather than only a queued one.
3. ~~**Move inference off the request path.**~~ **Done.** Engines declare
   `execution = "inline" | "queued"`; queued ones go to a depth-1 worker and answer `202`
   with a `public_id` the frontend polls, with progress and cancel. One GPU means one
   inference at a time, and that is now structural rather than hoped-for. Full reasoning
   in [ADR-0001](docs/adr/0001-phase-2-inference-execution.md).

   > Run a **single API worker** while a queued engine is active. Engines are module-level
   > singletons holding their own weights, so `--workers 2` loads the model twice.
4. **Progress in the UI.** `CameraStage` has the generate button and result modal;
   it needs a polling state and a progress indicator.
5. **Warm the cache.** Hashing is content-based, so the same pose + garment is free on
   the second hit. Pre-generate the current outfit while the user browses.
6. **IDM-VTON as the quality tier.** Same interface, heavier weights, offered as a
   second engine rather than a replacement.

### Phase 3 — Ideas beyond the brief

- Per-user measurement profile so `scale_multiplier` self-calibrates
- Garment segmentation on upload, so a photo of a real shirt becomes a catalog item
- Occlusion: use the pose segmentation mask to draw arms *over* the garment
- Depth-aware warping using the `z` coordinate MediaPipe already returns
- Record a short clip and export a try-on GIF
- Multi-person support (`numPoses > 1`)

---

## 9. Troubleshooting

**Camera is off / permission denied** — the browser remembers a denial per origin. Clear
it in site settings and reload. Only one app can hold the camera at a time.

**FPS below 30** — switch the pose model to `lite` and the delegate to `GPU` in the
settings panel. `heavy` on CPU is ~5 FPS, and that is expected.

**`StartGraph failed: ... kGpuService ... emscripten_webgl_create_context() returned
error 0`** — no WebGL2 (VM, headless, blocklisted driver). The app catches this and
retries on CPU automatically; the log line is noise, not a failure.

**Garments in the wrong place** — the fit sliders stack on top of the garment's own
calibration. Once it looks right, move the values into `catalog.json` so they persist.

**Catalog empty** — run `make clothes && make db`, or hit **Sync**.

**`npm audit` reports 2 moderate issues** — both are postcss, pulled in transitively by
Next 15. The fix is Next 16, which is a breaking upgrade; left alone deliberately.
