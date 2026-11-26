from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.storage.audit import serialize_audit_event
from app.storage.database import get_db
from app.storage.models import AuditEvent

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_audit_events(
    entity_type: str | None = None,
    outcome: Literal["success", "denied", "error"] | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type.strip())
    if outcome:
        query = query.where(AuditEvent.outcome == outcome)
    return [serialize_audit_event(event) for event in db.scalars(query.limit(limit)).all()]
