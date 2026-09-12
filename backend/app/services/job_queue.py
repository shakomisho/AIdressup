"""Depth-1 job queue for slow try-on engines (ADR-0001).

One GPU means one inference at a time. That is not a tuning parameter — running
two diffusions concurrently thrashes VRAM and then OOMs — so the queue has a
single consumer thread and that is the whole design.

Implementation note: the ADR sketched an ``asyncio.Queue`` driven from
``lifespan``. The route handlers are sync ``def``, so FastAPI already runs them
off the event loop in the anyio threadpool, and putting to an asyncio queue from
those threads would need ``call_soon_threadsafe`` round-trips. A plain
``queue.Queue`` plus one worker thread expresses the same guarantee with no
cross-thread hazards, so that is what this does.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass

from ..database import SessionLocal
from ..tryon import TryOnEngine, TryOnInput
from . import tryon_service

log = logging.getLogger("tryon.queue")


@dataclass(slots=True)
class Job:
    result_id: int
    engine: TryOnEngine
    engine_input: TryOnInput


#: ``None`` is the shutdown sentinel.
_queue: queue.Queue[Job | None] = queue.Queue()
_worker: threading.Thread | None = None
_lock = threading.Lock()


def _run_one(job: Job) -> None:
    """Own session per job: this thread is not the request's thread."""
    with SessionLocal() as db:
        try:
            tryon_service.execute(db, job.result_id, job.engine, job.engine_input)
        except Exception:  # noqa: BLE001 - already recorded on the row
            log.exception("try-on job %s failed", job.result_id)


def _consume() -> None:
    while True:
        job = _queue.get()
        try:
            if job is None:
                return
            _run_one(job)
        finally:
            _queue.task_done()


def start() -> None:
    global _worker
    with _lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_consume, name="tryon-worker", daemon=True)
        _worker.start()
        log.info("try-on job worker started (depth 1)")


def stop(timeout: float = 5.0) -> None:
    global _worker
    with _lock:
        if _worker is None:
            return
        _queue.put(None)
        _worker.join(timeout=timeout)
        if _worker.is_alive():
            log.warning("try-on worker still busy after %.1fs; abandoning it", timeout)
        _worker = None


def submit(job: Job) -> int:
    """Enqueue and return the number of jobs ahead of this one (0 = next up)."""
    if _worker is None or not _worker.is_alive():
        start()
    ahead = _queue.qsize()
    _queue.put(job)
    return ahead


def depth() -> int:
    return _queue.qsize()


def join(timeout: float | None = None) -> None:
    """Block until the queue drains. Tests only."""
    if timeout is None:
        _queue.join()
        return
    done = threading.Event()
    threading.Thread(target=lambda: (_queue.join(), done.set()), daemon=True).start()
    done.wait(timeout)
