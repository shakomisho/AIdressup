"""FastAPI application entry point.

Run: ``uvicorn app.main:app --reload --port 8000`` from the ``backend`` folder.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import settings
from .database import SessionLocal, init_db
from .routers import clothing, health, sessions, settings as settings_router, tryon
from .services import catalog, job_queue, tryon_service
from .tryon import get_engine, list_engines

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tryon")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    init_db()
    with SessionLocal() as db:
        report = catalog.sync_catalog(db)
        # The job queue lives in memory, so anything left mid-flight by a
        # previous process has no worker coming for it (ADR-0001).
        tryon_service.reap_orphans(db)
    log.info(
        "catalog synced: +%d ~%d -%d (%d active)",
        len(report["added"]),
        len(report["updated"]),
        len(report["deactivated"]),
        report["total_active"],
    )

    queued = [e for e in list_engines() if e.execution == "queued" and e.is_available()]
    if queued:
        # Engines are module-level singletons holding their own weights, so a
        # second uvicorn worker would load a second copy into VRAM.
        log.warning(
            "queued engine(s) active (%s) - run a single API worker; "
            "--workers > 1 loads the model weights once per process",
            ", ".join(e.name for e in queued),
        )

    job_queue.start()

    # Pay the weight-loading cost at boot rather than on the first request.
    try:
        get_engine(settings.default_engine).warmup()
    except Exception as exc:  # noqa: BLE001 - warmup is best-effort
        log.warning("warmup for %r skipped: %s", settings.default_engine, exc)

    try:
        yield
    finally:
        job_queue.stop()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Local-first virtual try-on API. Phase 1 = MediaPipe Pose landmark "
        "overlays; Phase 2 = pluggable diffusion try-on engines."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = app.router
app.include_router(health.router, prefix="/api")
app.include_router(clothing.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(tryon.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")

# Garment PNGs and generated results are served straight off disk.
app.mount(
    "/assets/clothes",
    StaticFiles(directory=str(settings.clothes_dir), check_dir=False),
    name="clothes",
)
app.mount(
    "/outputs",
    StaticFiles(directory=str(settings.output_dir), check_dir=False),
    name="outputs",
)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/api/health",
    }
