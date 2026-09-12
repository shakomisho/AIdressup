"""Try-on orchestration: cache lookup -> engine -> persisted result.

Split in two halves on purpose (ADR-0001):

``resolve``  is cheap and synchronous — garment lookup, image decode, hashing,
             cache probe, engine availability. Always runs inside the request.
``execute``  runs the engine. Inline for fast engines, on the job-queue worker
             thread for slow ones.

``run_tryon`` is the inline composition of both and remains the Phase 1 path.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ClothingItem, ResultCache, ResultStatus, TryOnResult, TryOnSession
from ..schemas import TryOnRequest
from ..tryon import EngineUnavailable, TryOnEngine, TryOnInput, get_engine
from . import catalog, images

log = logging.getLogger("tryon.service")


def _merge_params(item: ClothingItem, request_params: dict) -> dict:
    """Garment calibration is the baseline; the request may override per-frame."""
    merged = {
        "anchor_type": item.anchor_type.value,
        "scale_multiplier": item.scale_multiplier,
        "offset_x": item.offset_x,
        "offset_y": item.offset_y,
        "rotation_offset": item.rotation_offset,
        "pivot_x": item.pivot_x,
        "pivot_y": item.pivot_y,
        "opacity": item.opacity,
    }
    merged.update(request_params or {})
    return merged


@dataclass(slots=True)
class Resolved:
    """Outcome of admission. Either a cache hit, or a row ready to execute."""

    result: TryOnResult
    engine: TryOnEngine
    engine_input: TryOnInput
    cached: bool


def resolve(db: Session, payload: TryOnRequest) -> Resolved:
    """Admission control. Cheap, synchronous, and never runs the engine.

    Raises ``LookupError`` (unknown garment), ``ImageDecodeError`` (bad frame) or
    ``EngineUnavailable`` (missing deps/weights). Availability is checked *here*
    rather than inside ``generate`` because a queued engine runs on a worker
    thread, where a raised exception has no client left to answer.
    """
    item = db.get(ClothingItem, payload.clothing_id)
    if item is None:
        raise LookupError(f"clothing item {payload.clothing_id} not found")

    engine_name = payload.engine or settings.default_engine
    engine = get_engine(engine_name)
    if not engine.is_available():
        raise EngineUnavailable(engine.unavailable_reason())

    person_bytes, _mime = images.decode_image(payload.person_image)
    params = _merge_params(item, payload.params)

    engine_input = TryOnInput(
        person_image=person_bytes,
        garment_path=catalog.absolute_path(item),
        garment_category=item.category.value,
        garment_slug=item.slug,
        pose_landmarks=payload.pose_landmarks,
        params=params,
    )
    input_hash = images.sha256_hex(
        person_bytes, item.slug, *engine.cache_key_parts(engine_input)
    )

    # --- cache: must be probed before queueing, so a hit stays instant even
    #     for an engine that would otherwise cost 20 s -----------------------
    if settings.cache_enabled and payload.use_cache:
        cached = db.scalar(
            select(ResultCache).where(
                ResultCache.input_hash == input_hash, ResultCache.engine == engine_name
            )
        )
        if cached is not None and cached.result.status == ResultStatus.COMPLETED:
            cached.hit_count += 1
            cached.last_hit_at = datetime.now(timezone.utc)
            db.commit()
            return Resolved(cached.result, engine, engine_input, cached=True)

    session_row = None
    if payload.session_public_id:
        session_row = db.scalar(
            select(TryOnSession).where(TryOnSession.public_id == payload.session_public_id)
        )

    result = TryOnResult(
        session_id=session_row.id if session_row else None,
        clothing_item_id=item.id,
        engine=engine_name,
        status=ResultStatus.PENDING,
        input_hash=input_hash,
        pose_landmarks=payload.pose_landmarks,
        params=params,
    )
    db.add(result)
    db.commit()
    return Resolved(result, engine, engine_input, cached=False)


def execute(
    db: Session,
    result_id: int,
    engine: TryOnEngine,
    engine_input: TryOnInput,
) -> TryOnResult:
    """Run the engine for an already-admitted row and persist the outcome.

    Re-loads the row by id so it works with a session the caller owns — the
    queue worker runs on its own thread with its own session.
    """
    result = db.get(TryOnResult, result_id)
    if result is None:
        raise LookupError(f"try-on result {result_id} disappeared")

    if result.cancelled:
        result.status = ResultStatus.CANCELLED
        result.completed_at = datetime.now(timezone.utc)
        db.commit()
        return result

    result.status = ResultStatus.PROCESSING
    db.commit()

    started = time.perf_counter()
    try:
        output = engine.generate(engine_input)
    except Exception as exc:  # noqa: BLE001 - recorded on the row, then re-raised
        result.status = ResultStatus.FAILED
        result.error = (
            str(exc) if isinstance(exc, EngineUnavailable) else f"{type(exc).__name__}: {exc}"
        )
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        result.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise

    result.latency_ms = int((time.perf_counter() - started) * 1000)
    result.output_path = images.save_output(
        output.image, f"{result.public_id}.png", subdir=result.engine
    )
    result.status = ResultStatus.COMPLETED
    result.progress = 1.0
    result.completed_at = datetime.now(timezone.utc)
    db.add(
        ResultCache(input_hash=result.input_hash, engine=result.engine, result_id=result.id)
    )
    db.commit()
    return result


def run_tryon(db: Session, payload: TryOnRequest) -> tuple[TryOnResult, bool]:
    """Inline path: admit and run in one call. Returns ``(row, cache_hit)``."""
    resolved = resolve(db, payload)
    if resolved.cached:
        return resolved.result, True
    result = execute(db, resolved.result.id, resolved.engine, resolved.engine_input)
    return result, False


def reap_orphans(db: Session) -> int:
    """Fail rows left mid-flight by a dead process.

    The queue lives in memory, so anything still PENDING or PROCESSING at
    startup has no worker coming for it. Without this they poll forever.
    """
    stale = db.scalars(
        select(TryOnResult).where(
            TryOnResult.status.in_([ResultStatus.PENDING, ResultStatus.PROCESSING])
        )
    ).all()
    for row in stale:
        row.status = ResultStatus.FAILED
        row.error = "interrupted: server restarted while this job was in flight"
        row.completed_at = datetime.now(timezone.utc)
    if stale:
        db.commit()
        log.warning("reaped %d interrupted try-on job(s)", len(stale))
    return len(stale)


def request_cancel(db: Session, public_id: str) -> TryOnResult | None:
    """Flag a job as cancelled. Honoured before the engine starts.

    Interrupting an in-flight diffusion needs engine cooperation (a step
    callback that checks the flag); until an engine implements that, cancelling
    a PROCESSING job lets it finish and simply marks the intent.
    """
    row = db.scalar(select(TryOnResult).where(TryOnResult.public_id == public_id))
    if row is None:
        return None
    if row.status.is_terminal:
        return row
    row.cancelled = True
    if row.status == ResultStatus.PENDING:
        row.status = ResultStatus.CANCELLED
        row.completed_at = datetime.now(timezone.utc)
    db.commit()
    return row


def to_read_dict(result: TryOnResult, cached: bool = False) -> dict:
    return {
        "id": result.id,
        "public_id": result.public_id,
        "clothing_item_id": result.clothing_item_id,
        "engine": result.engine,
        "status": result.status,
        "input_hash": result.input_hash,
        "output_url": f"/outputs/{result.output_path}" if result.output_path else None,
        "latency_ms": result.latency_ms,
        "cached": cached,
        "error": result.error,
        "progress": result.progress,
        "cancelled": result.cancelled,
        "created_at": result.created_at,
    }


def cache_stats(db: Session) -> dict:
    entries = db.scalar(select(func.count()).select_from(ResultCache)) or 0
    hits = db.scalar(select(func.coalesce(func.sum(ResultCache.hit_count), 0))) or 0
    results = db.scalar(select(func.count()).select_from(TryOnResult)) or 0
    return {
        "entries": int(entries),
        "total_hits": int(hits),
        "results": int(results),
        "bytes_on_disk": images.dir_size(settings.output_dir),
    }


def clear_cache(db: Session, delete_files: bool = True) -> int:
    rows = db.scalars(select(TryOnResult)).all()
    removed = 0
    for row in rows:
        if delete_files and row.output_path:
            path = images.output_abs(row.output_path)
            if path.is_file():
                path.unlink()
        db.delete(row)
        removed += 1
    db.commit()
    return removed
