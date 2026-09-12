from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..config import settings
from ..database import get_db
from ..models import ClothingItem
from ..schemas import HealthRead
from ..tryon import engine_info

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthRead)
def health(db: Session = Depends(get_db)) -> HealthRead:
    count = db.scalar(
        select(func.count()).select_from(ClothingItem).where(ClothingItem.is_active.is_(True))
    )
    db_kind = settings.database_url.split(":", 1)[0]
    return HealthRead(
        status="ok",
        version=__version__,
        environment=settings.environment,
        database=db_kind,
        clothes_dir=str(settings.clothes_dir),
        catalog_items=int(count or 0),
        default_engine=settings.default_engine,
        engines=engine_info(),
    )
