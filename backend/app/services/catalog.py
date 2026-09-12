"""Catalog service: sync ``assets/clothes/`` into the database.

Folder layout is the source of truth::

    assets/clothes/
      shirts/white-tee.png
      pants/blue-jeans.png
      ...
      catalog.json          # optional per-item metadata overrides

Drop a PNG in, call ``POST /api/clothing/sync`` (or just restart the API) and
it shows up in the sidebar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import SLUG_PREFIX, AnchorType, Category, ClothingItem

IMAGE_SUFFIXES = {".png", ".webp"}
THUMB_SIZE = (320, 320)

# Sensible overlay defaults per category. ``pivot`` is the garment's own anchor
# point inside its PNG; ``scale`` is the garment width in units of the reference
# landmark distance (shoulder span / hip span / ear span / foot length / eye span).
CATEGORY_DEFAULTS: dict[Category, dict] = {
    Category.SHIRTS: {
        "anchor_type": AnchorType.TORSO,
        "scale_multiplier": 1.95,
        "offset_x": 0.0,
        "offset_y": -0.18,
        "pivot_x": 0.5,
        "pivot_y": 0.06,
        "z_index": 10,
    },
    Category.JACKETS: {
        "anchor_type": AnchorType.TORSO,
        "scale_multiplier": 2.25,
        "offset_x": 0.0,
        "offset_y": -0.22,
        "pivot_x": 0.5,
        "pivot_y": 0.05,
        "z_index": 20,
    },
    Category.PANTS: {
        "anchor_type": AnchorType.HIPS,
        "scale_multiplier": 1.75,
        "offset_x": 0.0,
        "offset_y": -0.12,
        "pivot_x": 0.5,
        "pivot_y": 0.04,
        "z_index": 5,
    },
    Category.HATS: {
        "anchor_type": AnchorType.HEAD,
        "scale_multiplier": 2.3,
        "offset_x": 0.0,
        "offset_y": -0.55,
        "pivot_x": 0.5,
        "pivot_y": 0.62,
        "z_index": 30,
    },
    Category.SHOES: {
        "anchor_type": AnchorType.FEET,
        "scale_multiplier": 1.5,
        "offset_x": 0.0,
        "offset_y": -0.1,
        "pivot_x": 0.5,
        "pivot_y": 0.35,
        "z_index": 25,
    },
    Category.GLASSES: {
        "anchor_type": AnchorType.EYES,
        # A frame is ~1.6x the outer-corner-to-outer-corner eye distance.
        "scale_multiplier": 1.6,
        "offset_x": 0.0,
        "offset_y": 0.0,
        # Bridge centre; the eye line runs through the middle of the lenses.
        "pivot_x": 0.5,
        "pivot_y": 0.5,
        # Above the face, below a hat brim.
        "z_index": 28,
    },
}

CATEGORY_LABELS = {
    Category.SHIRTS: "Shirts",
    Category.PANTS: "Pants",
    Category.JACKETS: "Jackets",
    Category.HATS: "Hats",
    Category.SHOES: "Shoes",
    Category.GLASSES: "Glasses",
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-{2,}", "-", value)


def humanize(stem: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_\s]+", stem) if part)


def _load_overrides() -> dict[str, dict]:
    path = settings.clothes_dir / "catalog.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    items = data.get("items", data) if isinstance(data, dict) else data
    if isinstance(items, list):
        return {entry["slug"]: entry for entry in items if "slug" in entry}
    return items if isinstance(items, dict) else {}


def _thumbnail_for(image_path: Path, rel_path: str) -> str | None:
    thumb_rel = f".thumbs/{rel_path.replace('/', '__')}"
    thumb_abs = settings.clothes_dir / thumb_rel
    thumb_abs.parent.mkdir(parents=True, exist_ok=True)
    if thumb_abs.is_file() and thumb_abs.stat().st_mtime >= image_path.stat().st_mtime:
        return thumb_rel
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGBA")
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            img.save(thumb_abs, format="PNG")
    except OSError:
        return None
    return thumb_rel


def discover_files() -> list[tuple[Category, Path]]:
    found: list[tuple[Category, Path]] = []
    for category in Category:
        folder = settings.clothes_dir / category.value
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                found.append((category, path))
    return found


def sync_catalog(db: Session) -> dict:
    """Reconcile disk -> DB. Returns a report of added/updated/deactivated slugs."""
    overrides = _load_overrides()
    existing = {item.slug: item for item in db.scalars(select(ClothingItem)).all()}
    seen: set[str] = set()
    added: list[str] = []
    updated: list[str] = []

    for category, path in discover_files():
        rel_path = f"{category.value}/{path.name}"
        slug = f"{SLUG_PREFIX[category]}-{slugify(path.stem)}"
        seen.add(slug)
        override = overrides.get(slug, overrides.get(rel_path, {}))

        try:
            with Image.open(path) as img:
                natural_width, natural_height = img.size
        except OSError:
            continue

        defaults = dict(CATEGORY_DEFAULTS[category])
        item = existing.get(slug)
        if item is None:
            item = ClothingItem(
                slug=slug,
                name=override.get("name") or humanize(path.stem),
                category=category,
                file_path=rel_path,
                **defaults,
            )
            db.add(item)
            added.append(slug)
        else:
            item.file_path = rel_path
            item.category = category
            if not item.is_active:
                item.is_active = True
            updated.append(slug)

        item.natural_width = natural_width
        item.natural_height = natural_height
        item.thumbnail_path = _thumbnail_for(path, rel_path)
        item.is_active = True

        # catalog.json wins over category defaults, for both metadata and tuning.
        for field in ("name", "brand", "color", "size", "description"):
            if override.get(field) is not None:
                setattr(item, field, override[field])
        if isinstance(override.get("tags"), list):
            item.tags = override["tags"]
        for field in (
            "scale_multiplier", "offset_x", "offset_y", "rotation_offset",
            "pivot_x", "pivot_y", "opacity", "z_index",
        ):
            if override.get(field) is not None:
                setattr(item, field, override[field])
        if override.get("anchor_type"):
            item.anchor_type = AnchorType(override["anchor_type"])

    deactivated: list[str] = []
    for slug, item in existing.items():
        if slug not in seen and item.is_active:
            item.is_active = False
            deactivated.append(slug)

    db.commit()
    total_active = len([s for s in seen])
    return {
        "added": added,
        "updated": updated,
        "deactivated": deactivated,
        "total_active": total_active,
    }


def absolute_path(item: ClothingItem) -> Path:
    return settings.clothes_dir / item.file_path


def to_read_dict(item: ClothingItem) -> dict:
    """ORM -> ClothingItemRead payload (adds URLs + nested overlay config)."""
    return {
        "id": item.id,
        "slug": item.slug,
        "name": item.name,
        "category": item.category,
        "file_path": item.file_path,
        "image_url": f"/assets/clothes/{item.file_path}",
        "thumbnail_url": (
            f"/assets/clothes/{item.thumbnail_path}" if item.thumbnail_path else None
        ),
        "natural_width": item.natural_width,
        "natural_height": item.natural_height,
        "brand": item.brand,
        "color": item.color,
        "size": item.size,
        "tags": item.tags or [],
        "description": item.description,
        "is_active": item.is_active,
        "overlay": {
            "anchor_type": item.anchor_type,
            "scale_multiplier": item.scale_multiplier,
            "offset_x": item.offset_x,
            "offset_y": item.offset_y,
            "rotation_offset": item.rotation_offset,
            "pivot_x": item.pivot_x,
            "pivot_y": item.pivot_y,
            "opacity": item.opacity,
            "z_index": item.z_index,
        },
        "created_at": item.created_at,
    }
