"""Try-on engine contract.

Everything the rest of the backend knows about generating a try-on image lives
behind :class:`TryOnEngine`. Phase 2 work = add a new subclass + register it;
no router, schema or frontend change required.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

#: ``inline``  - run inside the request; the response carries the finished image.
#: ``queued``  - hand to the depth-1 job queue and answer ``202``; the client polls.
ExecutionMode = Literal["inline", "queued"]


@dataclass(slots=True)
class TryOnInput:
    """Everything an engine needs to produce one try-on image."""

    person_image: bytes
    garment_path: Path
    garment_category: str
    garment_slug: str
    # MediaPipe Pose landmarks as sent by the browser, already normalised 0..1.
    pose_landmarks: dict | None = None
    params: dict = field(default_factory=dict)


@dataclass(slots=True)
class TryOnOutput:
    image: bytes
    mime_type: str = "image/png"
    meta: dict = field(default_factory=dict)


class TryOnEngine(abc.ABC):
    """Base class for every try-on backend."""

    #: registry key, e.g. ``"idm-vton"``
    name: str = "base"
    title: str = "Base engine"
    description: str = ""
    #: 1 = landmark overlay MVP, 2 = generative AI
    phase: int = 1
    #: pip packages / weights that must be present
    requires: list[str] = []
    #: How the API should run this engine. Sub-second engines stay ``inline``;
    #: anything that can occupy the GPU for seconds must be ``queued`` so that
    #: concurrent requests serialize instead of racing for VRAM. See ADR-0001.
    execution: ExecutionMode = "inline"

    def is_available(self) -> bool:
        """Cheap check used by ``GET /api/tryon/engines``. Never raises."""
        return True

    def unavailable_reason(self) -> str:
        """Message surfaced as the ``503`` body when :meth:`is_available` is False.

        Checked at admission time, before a job is queued — a queued engine runs
        on a worker thread, so an exception raised inside :meth:`generate` can
        never reach the client that asked for it.
        """
        return f"engine {self.name!r} is unavailable."

    def warmup(self) -> None:
        """Optional: load weights once at startup."""

    @abc.abstractmethod
    def generate(self, payload: TryOnInput) -> TryOnOutput:
        """Produce the try-on image. Raise :class:`EngineUnavailable` if it cannot."""

    def cache_key_parts(self, payload: TryOnInput) -> list[str]:
        """Extra strings folded into the cache hash (model revision, steps, ...)."""
        return [self.name]


class EngineUnavailable(RuntimeError):
    """Raised when an engine's dependencies or weights are missing."""
