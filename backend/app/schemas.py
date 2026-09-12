"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import AnchorType, Category, ResultStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# Clothing
# --------------------------------------------------------------------------
class ClothingOverlayConfig(ORMModel):
    anchor_type: AnchorType
    scale_multiplier: float
    offset_x: float
    offset_y: float
    rotation_offset: float
    pivot_x: float
    pivot_y: float
    opacity: float
    z_index: int


class ClothingItemRead(ORMModel):
    id: int
    slug: str
    name: str
    category: Category
    file_path: str
    image_url: str
    thumbnail_url: str | None = None
    natural_width: int | None = None
    natural_height: int | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    is_active: bool
    overlay: ClothingOverlayConfig
    created_at: datetime


class ClothingItemUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None
    anchor_type: AnchorType | None = None
    scale_multiplier: float | None = Field(default=None, ge=0.1, le=5.0)
    offset_x: float | None = Field(default=None, ge=-2.0, le=2.0)
    offset_y: float | None = Field(default=None, ge=-2.0, le=2.0)
    rotation_offset: float | None = Field(default=None, ge=-180.0, le=180.0)
    pivot_x: float | None = Field(default=None, ge=0.0, le=1.0)
    pivot_y: float | None = Field(default=None, ge=0.0, le=1.0)
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    z_index: int | None = None


class CategoryCount(BaseModel):
    category: Category
    label: str
    count: int


class SyncReport(BaseModel):
    added: list[str]
    updated: list[str]
    deactivated: list[str]
    total_active: int


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
class SessionCreate(BaseModel):
    user_agent: str | None = None
    camera_label: str | None = None
    frame_width: int | None = None
    frame_height: int | None = None


class SessionUpdate(BaseModel):
    avg_fps: float | None = None
    frames_processed: int | None = None
    notes: str | None = None
    ended: bool = False


class SessionRead(ORMModel):
    id: int
    public_id: str
    started_at: datetime
    ended_at: datetime | None
    user_agent: str | None
    camera_label: str | None
    frame_width: int | None
    frame_height: int | None
    avg_fps: float | None
    frames_processed: int


# --------------------------------------------------------------------------
# Try-on
# --------------------------------------------------------------------------
class TryOnRequest(BaseModel):
    """Phase 2 entry point. ``person_image`` is a data URL or bare base64 PNG/JPEG."""

    clothing_id: int
    person_image: str = Field(min_length=32)
    engine: str | None = None
    session_public_id: str | None = None
    pose_landmarks: dict | None = None
    params: dict = Field(default_factory=dict)
    use_cache: bool = True


class TryOnResultRead(ORMModel):
    id: int
    public_id: str
    clothing_item_id: int
    engine: str
    status: ResultStatus
    input_hash: str
    output_url: str | None = None
    latency_ms: int | None = None
    cached: bool = False
    error: str | None = None
    #: 0..1 while a queued engine runs; 1.0 once completed
    progress: float = 0.0
    cancelled: bool = False
    created_at: datetime


class EngineInfo(BaseModel):
    name: str
    title: str
    description: str
    available: bool
    phase: int
    requires: list[str] = Field(default_factory=list)
    #: "inline" -> POST returns the image; "queued" -> POST returns 202, poll
    execution: str = "inline"


class CacheStats(BaseModel):
    entries: int
    total_hits: int
    results: int
    bytes_on_disk: int


class QueueStats(BaseModel):
    depth: int


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
class SettingsPayload(BaseModel):
    values: dict


class HealthRead(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    clothes_dir: str
    catalog_items: int
    default_engine: str
    engines: list[EngineInfo]
