from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Category, ClothingItem
from ..schemas import CategoryCount, ClothingItemRead, ClothingItemUpdate, SyncReport
from ..services import catalog

router = APIRouter(prefix="/clothing", tags=["clothing"])


@router.get("", response_model=list[ClothingItemRead])
def list_clothing(
    db: Session = Depends(get_db),
    category: Category | None = Query(default=None),
    search: str | None = Query(default=None, max_length=80),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[ClothingItemRead]:
    stmt = select(ClothingItem)
    if not include_inactive:
        stmt = stmt.where(ClothingItem.is_active.is_(True))
    if category is not None:
        stmt = stmt.where(ClothingItem.category == category)
    if search:
        needle = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(ClothingItem.name).like(needle) | func.lower(ClothingItem.slug).like(needle)
        )
    stmt = stmt.order_by(ClothingItem.category, ClothingItem.name).limit(limit).offset(offset)
    return [ClothingItemRead(**catalog.to_read_dict(i)) for i in db.scalars(stmt).all()]


@router.get("/categories", response_model=list[CategoryCount])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryCount]:
    rows = dict(
        db.execute(
            select(ClothingItem.category, func.count())
            .where(ClothingItem.is_active.is_(True))
            .group_by(ClothingItem.category)
        ).all()
    )
    return [
        CategoryCount(
            category=c, label=catalog.CATEGORY_LABELS[c], count=int(rows.get(c, 0))
        )
        for c in Category
    ]


@router.post("/sync", response_model=SyncReport)
def sync(db: Session = Depends(get_db)) -> SyncReport:
    """Rescan ``assets/clothes/`` and reconcile the catalog table."""
    return SyncReport(**catalog.sync_catalog(db))


@router.get("/{item_id}", response_model=ClothingItemRead)
def get_clothing(item_id: int, db: Session = Depends(get_db)) -> ClothingItemRead:
    item = db.get(ClothingItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clothing item not found")
    return ClothingItemRead(**catalog.to_read_dict(item))


@router.patch("/{item_id}", response_model=ClothingItemRead)
def update_clothing(
    item_id: int, payload: ClothingItemUpdate, db: Session = Depends(get_db)
) -> ClothingItemRead:
    """Persist sidebar/settings-panel calibration tweaks for a garment."""
    item = db.get(ClothingItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clothing item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    return ClothingItemRead(**catalog.to_read_dict(item))


@router.post("", response_model=ClothingItemRead, status_code=status.HTTP_201_CREATED)
async def upload_clothing(
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    category: Category = Form(...),
    name: str | None = Form(default=None),
    brand: str | None = Form(default=None),
    color: str | None = Form(default=None),
) -> ClothingItemRead:
    """Add a garment PNG to the local catalog folder and index it."""
    suffix = (file.filename or "").lower().rsplit(".", 1)[-1]
    if suffix not in {"png", "webp"}:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "only transparent PNG or WebP garments are supported",
        )
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    stem = catalog.slugify((name or (file.filename or "garment").rsplit(".", 1)[0]))
    target_dir = settings.clothes_dir / category.value
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}.{suffix}"
    counter = 1
    while target.exists():
        target = target_dir / f"{stem}-{counter}.{suffix}"
        counter += 1
    target.write_bytes(data)

    catalog.sync_catalog(db)
    slug_prefix = category.value[:-1] if category.value.endswith("s") else category.value
    slug = f"{slug_prefix}-{catalog.slugify(target.stem)}"
    item = db.scalar(select(ClothingItem).where(ClothingItem.slug == slug))
    if item is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "catalog sync failed")
    if brand:
        item.brand = brand
    if color:
        item.color = color
    if name:
        item.name = name
    db.commit()
    return ClothingItemRead(**catalog.to_read_dict(item))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clothing(
    item_id: int,
    delete_file: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> None:
    item = db.get(ClothingItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clothing item not found")
    if delete_file:
        path = catalog.absolute_path(item)
        if path.is_file():
            path.unlink()
        db.delete(item)
    else:
        item.is_active = False
    db.commit()
