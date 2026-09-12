from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import TryOnResult
from ..schemas import CacheStats, EngineInfo, QueueStats, TryOnRequest, TryOnResultRead
from ..services import images, job_queue, tryon_service
from ..services.images import ImageDecodeError
from ..tryon import EngineUnavailable, engine_info

router = APIRouter(prefix="/tryon", tags=["tryon"])


@router.get("/engines", response_model=list[EngineInfo])
def engines() -> list[EngineInfo]:
    return [EngineInfo(**info) for info in engine_info()]


@router.post("", response_model=TryOnResultRead)
def create_tryon(
    payload: TryOnRequest, response: Response, db: Session = Depends(get_db)
) -> TryOnResultRead:
    """Generate a try-on image.

    Phase 1: ``engine="overlay"`` composites the PNG using the posted landmarks
    and returns ``200`` with the finished image — one call, one result.

    Phase 2: ``engine="catvton"`` / ``"idm-vton"`` take seconds, so they are
    admitted to a depth-1 queue and answered ``202`` with ``status="pending"``.
    Poll ``GET /api/tryon/{public_id}`` until the status is terminal. See
    ADR-0001.

    A cache hit always returns ``200`` immediately, whichever engine was asked
    for.
    """
    try:
        resolved = tryon_service.resolve(db, payload)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ImageDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except EngineUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc

    if resolved.cached:
        return TryOnResultRead(**tryon_service.to_read_dict(resolved.result, cached=True))

    if resolved.engine.execution == "queued":
        job_queue.submit(
            job_queue.Job(resolved.result.id, resolved.engine, resolved.engine_input)
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return TryOnResultRead(**tryon_service.to_read_dict(resolved.result))

    try:
        result = tryon_service.execute(
            db, resolved.result.id, resolved.engine, resolved.engine_input
        )
    except EngineUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc)) from exc
    return TryOnResultRead(**tryon_service.to_read_dict(result))


@router.get("/queue", response_model=QueueStats)
def queue_stats() -> QueueStats:
    return QueueStats(depth=job_queue.depth())


@router.get("/results", response_model=list[TryOnResultRead])
def list_results(
    db: Session = Depends(get_db),
    clothing_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[TryOnResultRead]:
    stmt = select(TryOnResult).order_by(TryOnResult.created_at.desc()).limit(limit)
    if clothing_id is not None:
        stmt = stmt.where(TryOnResult.clothing_item_id == clothing_id)
    return [TryOnResultRead(**tryon_service.to_read_dict(r)) for r in db.scalars(stmt).all()]


@router.get("/cache", response_model=CacheStats)
def cache(db: Session = Depends(get_db)) -> CacheStats:
    return CacheStats(**tryon_service.cache_stats(db))


@router.delete("/cache")
def clear_cache(db: Session = Depends(get_db)) -> dict:
    removed = tryon_service.clear_cache(db)
    return {"removed": removed}


@router.get("/{public_id}", response_model=TryOnResultRead)
def get_result(public_id: str, db: Session = Depends(get_db)) -> TryOnResultRead:
    row = db.scalar(select(TryOnResult).where(TryOnResult.public_id == public_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "result not found")
    return TryOnResultRead(**tryon_service.to_read_dict(row))


@router.post("/{public_id}/cancel", response_model=TryOnResultRead)
def cancel_result(public_id: str, db: Session = Depends(get_db)) -> TryOnResultRead:
    """Ask for a queued job to be dropped.

    A job that has not started yet goes straight to ``cancelled``. One already
    running is only flagged — interrupting mid-diffusion needs the engine to
    check the flag from its step callback.
    """
    row = tryon_service.request_cancel(db, public_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "result not found")
    return TryOnResultRead(**tryon_service.to_read_dict(row))


@router.get("/{public_id}/image")
def get_result_image(public_id: str, db: Session = Depends(get_db)) -> FileResponse:
    row = db.scalar(select(TryOnResult).where(TryOnResult.public_id == public_id))
    if row is None or not row.output_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "result image not found")
    path = images.output_abs(row.output_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "result image missing on disk")
    return FileResponse(path, media_type="image/png", filename=f"{public_id}.png")
