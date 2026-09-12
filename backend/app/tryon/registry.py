"""Engine registry — the single plug-in point for new try-on models."""

from __future__ import annotations

from .base import EngineUnavailable, TryOnEngine
from .catvton_engine import CatVTONEngine
from .idm_vton_engine import IDMVTONEngine
from .overlay_engine import OverlayEngine

_ENGINES: dict[str, TryOnEngine] = {}


def register(engine: TryOnEngine) -> TryOnEngine:
    _ENGINES[engine.name] = engine
    return engine


register(OverlayEngine())
register(CatVTONEngine())
register(IDMVTONEngine())


def get_engine(name: str) -> TryOnEngine:
    try:
        return _ENGINES[name]
    except KeyError:
        raise EngineUnavailable(f"unknown engine {name!r}") from None


def list_engines() -> list[TryOnEngine]:
    return sorted(_ENGINES.values(), key=lambda e: (e.phase, e.name))


def engine_info() -> list[dict]:
    out = []
    for engine in list_engines():
        try:
            available = engine.is_available()
        except Exception:  # never let a broken optional dep break the endpoint
            available = False
        out.append(
            {
                "name": engine.name,
                "title": engine.title,
                "description": engine.description,
                "available": available,
                "phase": engine.phase,
                "requires": list(engine.requires),
                "execution": engine.execution,
            }
        )
    return out
