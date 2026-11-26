import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.publish import create_publish_snapshot
from app.config import get_settings
from app.core.media.video import VideoError
from app.queue_scheduler.manager import queue_manager
from app.storage.audit import add_audit_event
from app.storage.database import SessionLocal, get_db
from app.storage.models import (
    Account,
    ComplianceDecision,
    Draft,
    Preset,
    PublishLog,
    PublishTask,
    SchedulePlan,
)
from publishers.registry import get_adapter

router = APIRouter(tags=["schedules"])
settings = get_settings()
timezone = ZoneInfo(settings.schedule_timezone)


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    draft_id: int
    account_ids: list[int] = Field(min_length=1, max_length=20)
    preset_id: str = "fresh"
    cron_expr: str | None = Field(default=None, max_length=80)
    scheduled_at: datetime | None = None
    authorized: bool = False


class ScheduleToggle(BaseModel):
    enabled: bool


def serialize_plan(plan: SchedulePlan, db: Session) -> dict:
    account_ids = json.loads(plan.account_ids)
    accounts = db.scalars(select(Account).where(Account.id.in_(account_ids))).all()
    draft = db.get(Draft, plan.draft_id)
    preset = db.get(Preset, plan.preset_id)
    authorization_valid = False
    if plan.authorized_fingerprint and draft and preset:
        try:
            snapshot, _ = create_publish_snapshot(draft, preset, db)
            authorization_valid = snapshot["content_sha256"] == plan.authorized_fingerprint
        except VideoError:
            authorization_valid = False
    return {
        "id": plan.id,
        "name": plan.name,
        "draft_id": plan.draft_id,
        "draft_title": draft.title if draft else "草稿已删除",
        "content_type": draft.content_type if draft else "article",
        "account_ids": account_ids,
        "account_names": [account.nickname for account in accounts],
        "preset_id": plan.preset_id,
        "cron_expr": plan.cron_expr,
        "scheduled_at": plan.scheduled_at.isoformat() if plan.scheduled_at else None,
        "enabled": plan.enabled,
        "authorized": plan.authorized,
        "authorization_valid": authorization_valid,
        "last_run_at": plan.last_run_at.isoformat() if plan.last_run_at else None,
        "next_run_at": plan.next_run_at.isoformat() if plan.next_run_at else None,
        "created_at": plan.created_at.isoformat(),
    }


@router.get("/schedules")
def list_schedules(db: Session = Depends(get_db)):
    plans = db.scalars(select(SchedulePlan).order_by(SchedulePlan.created_at.desc())).all()
    return [serialize_plan(plan, db) for plan in plans]


@router.post("/schedules", status_code=201)
def create_schedule(request: ScheduleCreate, db: Session = Depends(get_db)):
    if not settings.publishing_enabled:
        raise HTTPException(503, "当前运行模式已禁用真实发布，请在带可见浏览器的本机模式创建计划。")
    draft = db.get(Draft, request.draft_id)
    preset = db.get(Preset, request.preset_id)
    if not draft or not preset:
        raise HTTPException(404, "草稿或排版预设不存在")
    if not request.authorized:
        raise HTTPException(400, "请确认内容归属与平台自动化授权")
    if not draft.title.strip():
        raise HTTPException(400, "标题不能为空")
    if draft.content_type != "video" and not draft.body.strip():
        raise HTTPException(400, "正文不能为空")
    try:
        snapshot, findings = create_publish_snapshot(draft, preset, db)
    except VideoError as exc:
        raise HTTPException(400, str(exc)) from exc
    if any(item["type"] == "prohibited" for item in findings):
        raise HTTPException(400, "内容包含禁止发布项，已拦截")
    if any(item["type"] == "advertising" for item in findings):
        raise HTTPException(400, "请先修改广告法风险用语，再创建定时计划")
    if bool(request.cron_expr) == bool(request.scheduled_at):
        raise HTTPException(400, "请选择一次性定时或周期计划中的一种")
    accounts = db.scalars(select(Account).where(Account.id.in_(request.account_ids))).all()
    if len(accounts) != len(set(request.account_ids)):
        raise HTTPException(404, "部分发布账号不存在")
    for account in accounts:
        try:
            adapter = get_adapter(account.platform)
        except (ImportError, ValueError) as exc:
            raise HTTPException(400, f"暂不支持账号平台：{account.platform}") from exc
        if draft.content_type not in adapter.content_types:
            raise HTTPException(400, f"{adapter.display_name} 不支持此内容类型。")
        if (
            draft.content_type == "video"
            and adapter.title_limit
            and len(draft.title) > adapter.title_limit
        ):
            raise HTTPException(
                400, f"{adapter.display_name} 标题不能超过 {adapter.title_limit} 个字符。"
            )
    if request.cron_expr:
        try:
            CronTrigger.from_crontab(request.cron_expr, timezone=timezone)
        except ValueError as exc:
            raise HTTPException(400, "Cron 表达式无效，请使用 5 段格式，例如 30 9 * * *") from exc
    else:
        scheduled = (
            request.scheduled_at.astimezone(timezone).replace(tzinfo=None)
            if request.scheduled_at.tzinfo
            else request.scheduled_at
        )
        now = datetime.now(timezone).replace(tzinfo=None)
        if scheduled <= now + timedelta(seconds=5):
            raise HTTPException(400, "定时时间至少需要晚于当前时间 5 秒")
        if scheduled > now + timedelta(days=366):
            raise HTTPException(400, "定时时间不能超过一年")
    plan = SchedulePlan(
        name=request.name,
        draft_id=draft.id,
        account_ids=json.dumps(sorted(set(request.account_ids))),
        preset_id=preset.id,
        cron_expr=request.cron_expr,
        scheduled_at=scheduled if request.scheduled_at else None,
        authorized=True,
        authorized_fingerprint=snapshot["content_sha256"],
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    queue_manager.register_plan(plan.id)
    return serialize_plan(plan, db)


@router.patch("/schedules/{plan_id}")
def toggle_schedule(plan_id: int, request: ScheduleToggle, db: Session = Depends(get_db)):
    if request.enabled and not settings.publishing_enabled:
        raise HTTPException(503, "当前运行模式已禁用真实发布，不能在容器模式启用计划。")
    plan = db.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(404, "调度计划不存在")
    if (
        request.enabled
        and plan.scheduled_at
        and plan.scheduled_at <= datetime.now(timezone).replace(tzinfo=None)
    ):
        raise HTTPException(409, "一次性计划已过期，不能重新启用")
    if request.enabled:
        draft = db.get(Draft, plan.draft_id)
        preset = db.get(Preset, plan.preset_id)
        if not draft or not preset or not plan.authorized_fingerprint:
            raise HTTPException(409, "计划授权已失效，请重新创建计划。")
        try:
            snapshot, findings = create_publish_snapshot(draft, preset, db)
        except VideoError as exc:
            raise HTTPException(409, str(exc)) from exc
        if snapshot["content_sha256"] != plan.authorized_fingerprint or any(
            item["type"] in {"prohibited", "advertising"} for item in findings
        ):
            raise HTTPException(409, "草稿、模板或媒体已变化，请重新确认授权并创建计划。")
    plan.enabled = request.enabled
    db.commit()
    if request.enabled:
        queue_manager.register_plan(plan.id)
    else:
        queue_manager.remove_plan(plan.id)
    db.refresh(plan)
    return serialize_plan(plan, db)


@router.delete("/schedules/{plan_id}", status_code=204)
def delete_schedule(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(404, "调度计划不存在")
    queue_manager.remove_plan(plan_id)
    for task in db.scalars(
        select(PublishTask).where(PublishTask.schedule_plan_id == plan_id)
    ).all():
        task.schedule_plan_id = None
    db.delete(plan)
    db.commit()


def create_plan_tasks(plan_id: int, slot: str) -> list[int]:
    task_ids: list[int] = []
    now = datetime.now(timezone).replace(tzinfo=None)
    interval = timedelta(seconds=settings.min_publish_interval_seconds)
    with SessionLocal.begin() as db:
        plan = db.get(SchedulePlan, plan_id)
        if not plan or not plan.enabled or not plan.authorized:
            return task_ids
        if not settings.publishing_enabled:
            plan.enabled = False
            plan.next_run_at = None
            add_audit_event(
                db,
                action="schedule.authorization",
                entity_type="schedule_plan",
                entity_id=plan_id,
                outcome="denied",
                message="当前运行模式已禁用真实发布，计划已停用。",
            )
            return task_ids
        draft = db.get(Draft, plan.draft_id)
        preset = db.get(Preset, plan.preset_id)
        if not draft or not preset:
            return task_ids
        try:
            snapshot, findings = create_publish_snapshot(draft, preset, db)
        except VideoError:
            return task_ids
        fingerprint = snapshot["content_sha256"]
        if not plan.authorized_fingerprint or fingerprint != plan.authorized_fingerprint:
            plan.enabled = False
            plan.next_run_at = None
            message = "草稿、模板或媒体已变化，原授权失效，计划已停用。"
            add_audit_event(
                db,
                action="schedule.authorization",
                entity_type="schedule_plan",
                entity_id=plan_id,
                outcome="denied",
                message=message,
            )
            return task_ids
        if any(item["type"] in {"prohibited", "advertising"} for item in findings):
            plan.enabled = False
            plan.next_run_at = None
            add_audit_event(
                db,
                action="schedule.compliance",
                entity_type="schedule_plan",
                entity_id=plan_id,
                outcome="denied",
                message="执行前合规校验未通过，计划已停用。",
            )
            return task_ids
        account_ids = json.loads(plan.account_ids)
        accounts = db.scalars(select(Account).where(Account.id.in_(account_ids))).all()
        account_map = {account.id: account for account in accounts}
        run_slot = plan.scheduled_at.strftime("%Y%m%d%H%M") if plan.scheduled_at else slot
        for index, account_id in enumerate(account_ids):
            account = account_map.get(account_id)
            if not account:
                continue
            try:
                if draft.content_type not in get_adapter(account.platform).content_types:
                    continue
            except (ImportError, ValueError):
                continue
            run_key = f"plan-{plan_id}:{run_slot}:{account_id}"
            if db.scalar(select(PublishTask.id).where(PublishTask.run_key == run_key)):
                continue
            run_at = now + interval * index
            latest = db.scalar(
                select(PublishTask)
                .where(
                    PublishTask.account_id == account_id,
                    PublishTask.status.in_(["pending", "running"]),
                )
                .order_by(PublishTask.created_at.desc())
            )
            if latest:
                latest_time = latest.scheduled_at or latest.created_at
                run_at = max(run_at, latest_time + interval)
            task = PublishTask(
                draft_id=draft.id,
                account_id=account.id,
                platform=account.platform,
                content_type=draft.content_type,
                preset_id=plan.preset_id,
                scheduled_at=run_at,
                schedule_plan_id=plan.id,
                run_key=run_key,
                snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                max_retries=settings.max_retries,
            )
            db.add(task)
            db.flush()
            db.add(
                ComplianceDecision(
                    task_id=task.id,
                    content_sha256=fingerprint,
                    ruleset_version=settings.compliance_ruleset_version,
                    passed=True,
                    findings_json=json.dumps(findings, ensure_ascii=False),
                    ad_acknowledged=False,
                )
            )
            db.add(
                PublishLog(
                    task_id=task.id,
                    level="info",
                    message=f"调度计划「{plan.name}」创建任务，并已启用账号错峰。",
                )
            )
            task_ids.append(task.id)
        plan.last_run_at = now
        if plan.scheduled_at:
            plan.enabled = False
            plan.next_run_at = None
    for task_id in task_ids:
        queue_manager.enqueue(task_id)
    return task_ids
