from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import TryOnSession
from ..schemas import SessionCreate, SessionRead, SessionUpdate

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> SessionRead:
    row = TryOnSession(**payload.model_dump())
    db.add(row)
    db.commit()
    return SessionRead.model_validate(row)


@router.get("", response_model=list[SessionRead])
def list_sessions(
    db: Session = Depends(get_db), limit: int = Query(default=25, ge=1, le=200)
) -> list[SessionRead]:
    stmt = select(TryOnSession).order_by(TryOnSession.started_at.desc()).limit(limit)
    return [SessionRead.model_validate(r) for r in db.scalars(stmt).all()]


def _get(db: Session, public_id: str) -> TryOnSession:
    row = db.scalar(select(TryOnSession).where(TryOnSession.public_id == public_id))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return row


@router.get("/{public_id}", response_model=SessionRead)
def get_session(public_id: str, db: Session = Depends(get_db)) -> SessionRead:
    return SessionRead.model_validate(_get(db, public_id))


@router.patch("/{public_id}", response_model=SessionRead)
def update_session(
    public_id: str, payload: SessionUpdate, db: Session = Depends(get_db)
) -> SessionRead:
    """Frontend reports rolling FPS / frame counts here; ``ended=true`` closes it."""
    row = _get(db, public_id)
    data = payload.model_dump(exclude_unset=True)
    if data.pop("ended", False):
        row.ended_at = datetime.now(timezone.utc)
    for field, value in data.items():
        setattr(row, field, value)
    db.commit()
    return SessionRead.model_validate(row)
