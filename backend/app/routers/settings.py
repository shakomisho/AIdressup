from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings as app_config
from ..database import get_db
from ..models import AppSetting
from ..schemas import SettingsPayload

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULTS: dict = {
    "showSkeleton": True,
    "showLandmarks": True,
    "showClothing": True,
    "mirror": True,
    "smoothing": 0.6,
    "clothingOpacity": 1.0,
    "scaleAdjust": 1.0,
    "offsetX": 0.0,
    "offsetY": 0.0,
    "modelVariant": "lite",
    "delegate": "GPU",
    "targetFps": 30,
    "showFps": True,
    "engine": app_config.default_engine,
}


@router.get("", response_model=SettingsPayload)
def read_settings(db: Session = Depends(get_db)) -> SettingsPayload:
    stored = {row.key: row.value for row in db.scalars(select(AppSetting)).all()}
    return SettingsPayload(values={**DEFAULTS, **stored})


@router.put("", response_model=SettingsPayload)
def write_settings(payload: SettingsPayload, db: Session = Depends(get_db)) -> SettingsPayload:
    """Upsert only the provided keys; unknown keys are ignored."""
    for key, value in payload.values.items():
        if key not in DEFAULTS:
            continue
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    stored = {row.key: row.value for row in db.scalars(select(AppSetting)).all()}
    return SettingsPayload(values={**DEFAULTS, **stored})


@router.delete("", response_model=SettingsPayload)
def reset_settings(db: Session = Depends(get_db)) -> SettingsPayload:
    for row in db.scalars(select(AppSetting)).all():
        db.delete(row)
    db.commit()
    return SettingsPayload(values=dict(DEFAULTS))
