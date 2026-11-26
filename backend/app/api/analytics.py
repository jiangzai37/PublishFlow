from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import MetricSnapshotRequest
from app.storage.database import get_db
from app.storage.models import Draft, MetricSnapshot, PublishTask

router = APIRouter(tags=["analytics"])
METRIC_FIELDS = ("views", "reads", "plays", "likes", "comments", "shares", "favorites")
COLLECTION_NOTICE = "仅支持手工录入、平台官方导出或授权 API；不爬取私密页面，不绕过平台限制。"


def serialize_snapshot(snapshot: MetricSnapshot, title: str = "") -> dict:
    return {
        "id": snapshot.id,
        "task_id": snapshot.task_id,
        "platform": snapshot.platform,
        "draft_title": title,
        "metric_date": snapshot.metric_date.isoformat(),
        "source": snapshot.source,
        **{field: getattr(snapshot, field) for field in METRIC_FIELDS},
        "note": snapshot.note,
        "collected_at": snapshot.collected_at.isoformat(),
    }


@router.post("/metrics", status_code=201)
def upsert_metric_snapshot(request: MetricSnapshotRequest, db: Session = Depends(get_db)):
    task = db.get(PublishTask, request.task_id)
    if not task:
        raise HTTPException(404, "发布任务不存在")
    if task.status != "success":
        raise HTTPException(409, "只有已成功发布的任务可以录入平台数据")
    if request.metric_date > date.today():
        raise HTTPException(400, "指标日期不能晚于今天")
    snapshot = db.scalar(
        select(MetricSnapshot).where(
            MetricSnapshot.task_id == task.id,
            MetricSnapshot.metric_date == request.metric_date,
            MetricSnapshot.source == request.source,
        )
    )
    if snapshot is None:
        snapshot = MetricSnapshot(task_id=task.id, platform=task.platform)
        db.add(snapshot)
    snapshot.metric_date = request.metric_date
    snapshot.source = request.source
    for field in METRIC_FIELDS:
        setattr(snapshot, field, getattr(request, field))
    snapshot.note = request.note.strip()
    snapshot.collected_at = datetime.now()
    db.commit()
    db.refresh(snapshot)
    draft = db.get(Draft, task.draft_id)
    return serialize_snapshot(snapshot, draft.title if draft else "")


@router.get("/metrics")
def list_metric_snapshots(
    task_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(MetricSnapshot).order_by(
        MetricSnapshot.metric_date.desc(), MetricSnapshot.collected_at.desc()
    )
    if task_id:
        query = query.where(MetricSnapshot.task_id == task_id)
    snapshots = db.scalars(query.limit(limit)).all()
    task_ids = {snapshot.task_id for snapshot in snapshots}
    tasks = {
        task.id: task
        for task in db.scalars(select(PublishTask).where(PublishTask.id.in_(task_ids))).all()
    }
    draft_ids = {task.draft_id for task in tasks.values()}
    drafts = {
        draft.id: draft for draft in db.scalars(select(Draft).where(Draft.id.in_(draft_ids))).all()
    }
    return [
        serialize_snapshot(
            snapshot,
            drafts.get(tasks[snapshot.task_id].draft_id).title
            if snapshot.task_id in tasks and tasks[snapshot.task_id].draft_id in drafts
            else "",
        )
        for snapshot in snapshots
    ]


@router.get("/analytics")
def analytics_overview(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    today = date.today()
    since_date = today - timedelta(days=days - 1)
    tasks = db.scalars(select(PublishTask).order_by(PublishTask.created_at.desc())).all()
    period_tasks = [task for task in tasks if task.created_at.date() >= since_date]
    status_counts = Counter(task.status for task in period_tasks)
    total = len(tasks)
    period_total = len(period_tasks)
    success = status_counts["success"]
    trend = {
        since_date + timedelta(days=offset): {"total": 0, "success": 0, "failed": 0}
        for offset in range(days)
    }
    platforms: dict[str, dict] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
    content_types: Counter = Counter()
    for task in period_tasks:
        platform = platforms[task.platform]
        platform["total"] += 1
        platform[task.status] = platform.get(task.status, 0) + 1
        content_types[task.content_type] += 1
        task_date = task.created_at.date()
        if task_date in trend:
            trend[task_date]["total"] += 1
            if task.status in {"success", "failed"}:
                trend[task_date][task.status] += 1

    snapshots = db.scalars(
        select(MetricSnapshot)
        .where(MetricSnapshot.metric_date >= since_date)
        .order_by(MetricSnapshot.collected_at.asc())
    ).all()
    latest_by_day = {}
    for snapshot in snapshots:
        latest_by_day[(snapshot.task_id, snapshot.metric_date)] = snapshot
    totals = {field: 0 for field in METRIC_FIELDS}
    for snapshot in latest_by_day.values():
        for field in METRIC_FIELDS:
            totals[field] += getattr(snapshot, field)
    reach = totals["views"] + totals["reads"] + totals["plays"]
    engagement = totals["likes"] + totals["comments"] + totals["shares"] + totals["favorites"]

    recent = db.scalars(
        select(MetricSnapshot).order_by(MetricSnapshot.collected_at.desc()).limit(10)
    ).all()
    task_map = {task.id: task for task in tasks}
    draft_ids = {
        task_map[snapshot.task_id].draft_id for snapshot in recent if snapshot.task_id in task_map
    }
    drafts = {
        draft.id: draft for draft in db.scalars(select(Draft).where(Draft.id.in_(draft_ids))).all()
    }

    return {
        "generated_at": datetime.now().isoformat(),
        "period_days": days,
        "summary": {
            "total_tasks": total,
            "period_tasks": period_total,
            "success": success,
            "failed": status_counts["failed"],
            "active": status_counts["pending"] + status_counts["running"] + status_counts["paused"],
            "skipped": status_counts["skipped"],
            "success_rate": round(success / period_total * 100, 1) if period_total else 0,
        },
        "status_counts": dict(status_counts),
        "content_types": dict(content_types),
        "platforms": [
            {"platform": platform, **counts}
            for platform, counts in sorted(
                platforms.items(), key=lambda item: item[1]["total"], reverse=True
            )
        ],
        "trend": [{"date": day.isoformat(), **counts} for day, counts in trend.items()],
        "metrics": {
            **totals,
            "reach": reach,
            "engagement": engagement,
            "engagement_rate": round(engagement / reach * 100, 2) if reach else 0,
            "snapshots": len(latest_by_day),
        },
        "recent_metrics": [
            serialize_snapshot(
                snapshot,
                drafts.get(task_map[snapshot.task_id].draft_id).title
                if snapshot.task_id in task_map and task_map[snapshot.task_id].draft_id in drafts
                else "",
            )
            for snapshot in recent
        ],
        "collection_notice": COLLECTION_NOTICE,
    }
