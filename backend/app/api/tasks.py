from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.publish import serialize_task
from app.storage.database import get_db
from app.storage.models import PublishTask

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
def list_tasks(
    status: Literal["pending", "running", "success", "failed", "paused", "skipped"] | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(PublishTask).order_by(desc(PublishTask.created_at))
    if status:
        query = query.where(PublishTask.status == status)
    tasks = db.scalars(query.limit(limit)).all()
    return [serialize_task(task, db) for task in tasks]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(PublishTask, task_id)
    if not task:
        from fastapi import HTTPException

        raise HTTPException(404, "任务不存在")
    return serialize_task(task, db)
