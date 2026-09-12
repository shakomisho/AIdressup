"""ORM models.

Schema overview
---------------
clothing_items   one row per garment PNG in assets/clothes/<category>/
tryon_sessions   one row per webcam session started by the frontend
tryon_results    one row per generated try-on image (Phase 2) or snapshot
result_cache     input-hash -> tryon_result lookup so AI work is never repeated
app_settings     key/value store for user preferences (overlay tuning, engine)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(str, enum.Enum):
    SHIRTS = "shirts"
    PANTS = "pants"
    JACKETS = "jackets"
    HATS = "hats"
    SHOES = "shoes"
    GLASSES = "glasses"


#: Slug prefix per category. Item slugs are ``<prefix>-<filename>``, and naive
#: de-pluralising would turn ``glasses`` into ``glasse``, so spell them all out.
SLUG_PREFIX: dict[Category, str] = {
    Category.SHIRTS: "shirt",
    Category.PANTS: "pant",
    Category.JACKETS: "jacket",
    Category.HATS: "hat",
    Category.SHOES: "shoe",
    Category.GLASSES: "glasses",
}


class AnchorType(str, enum.Enum):
    """Which pose landmarks drive the overlay transform."""

    TORSO = "torso"          # shoulders + hips      -> shirts, jackets
    HIPS = "hips"            # hips + knees/ankles   -> pants
    HEAD = "head"            # ears + shoulders      -> hats
    FEET = "feet"            # ankle + foot index    -> shoes (rendered twice)
    EYES = "eyes"            # eye corners           -> glasses


class ResultStatus(str, enum.Enum):
    #: accepted and queued, engine not started (queued engines only)
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    #: cancelled before the engine started; distinct from FAILED so the UI can
    #: stay quiet about it. The ``cancelled`` column is the *request*; this is
    #: the outcome.
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (
            ResultStatus.COMPLETED,
            ResultStatus.FAILED,
            ResultStatus.CANCELLED,
        )


class ClothingItem(Base):
    __tablename__ = "clothing_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[Category] = mapped_column(
        Enum(Category, values_callable=lambda e: [m.value for m in e]), index=True
    )

    # Paths are relative to settings.clothes_dir, e.g. "shirts/white-tee.png".
    file_path: Mapped[str] = mapped_column(String(512))
    thumbnail_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    natural_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    natural_height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Phase 1 overlay calibration -------------------------------------
    anchor_type: Mapped[AnchorType] = mapped_column(
        Enum(AnchorType, values_callable=lambda e: [m.value for m in e]),
        default=AnchorType.TORSO,
    )
    # Garment width as a multiple of the reference landmark distance
    # (shoulder span for torso, hip span for hips, ear span for head).
    scale_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    # Fine tuning, expressed in fractions of the reference distance.
    offset_x: Mapped[float] = mapped_column(Float, default=0.0)
    offset_y: Mapped[float] = mapped_column(Float, default=0.0)
    rotation_offset: Mapped[float] = mapped_column(Float, default=0.0)  # degrees
    # Where the garment's own anchor point sits inside the PNG (0..1).
    pivot_x: Mapped[float] = mapped_column(Float, default=0.5)
    pivot_y: Mapped[float] = mapped_column(Float, default=0.08)
    opacity: Mapped[float] = mapped_column(Float, default=1.0)
    z_index: Mapped[int] = mapped_column(Integer, default=10)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    results: Mapped[list["TryOnResult"]] = relationship(
        back_populates="clothing_item", cascade="all, delete-orphan"
    )


class TryOnSession(Base):
    __tablename__ = "tryon_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    camera_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    frame_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    frames_processed: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    results: Mapped[list["TryOnResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class TryOnResult(Base):
    __tablename__ = "tryon_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("tryon_sessions.id", ondelete="CASCADE"), nullable=True
    )
    clothing_item_id: Mapped[int] = mapped_column(
        ForeignKey("clothing_items.id", ondelete="CASCADE"), index=True
    )

    engine: Mapped[str] = mapped_column(String(40), default="overlay", index=True)
    status: Mapped[ResultStatus] = mapped_column(
        Enum(ResultStatus, values_callable=lambda e: [m.value for m in e]),
        default=ResultStatus.PENDING,
        index=True,
    )
    # sha256 of (person image bytes + garment slug + engine + params)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    person_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pose_landmarks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 0..1, written by queued engines from their diffusion step callback so the
    # UI has something to show across a 5-20 s run. Inline engines skip it.
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    session: Mapped[TryOnSession | None] = relationship(back_populates="results")
    clothing_item: Mapped[ClothingItem] = relationship(back_populates="results")


class ResultCache(Base):
    """Dedupe table: identical input never re-runs an expensive AI model."""

    __tablename__ = "result_cache"
    __table_args__ = (
        UniqueConstraint("input_hash", "engine", name="uq_result_cache_hash_engine"),
        Index("ix_result_cache_lookup", "input_hash", "engine"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(40))
    result_id: Mapped[int] = mapped_column(
        ForeignKey("tryon_results.id", ondelete="CASCADE")
    )
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_hit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    result: Mapped[TryOnResult] = relationship()


class AppSetting(Base):
    """Single-table key/value preferences, mirrors the frontend settings panel."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
