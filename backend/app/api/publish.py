import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.credentials import CredentialVault
from app.config import get_settings
from app.core.compliance.validator import content_fingerprint, file_sha256, validate_content
from app.core.media.video import VideoError, VideoMetadata, validate_video
from app.core.typesetting.engine import plain_text_from_html, render_article
from app.core.typesetting.presets import resolve_preset
from app.queue_scheduler.manager import queue_manager
from app.storage.audit import add_audit_event, log_task_event, sanitize_text, sanitize_url
from app.storage.database import SessionLocal, get_db
from app.storage.models import Account, ComplianceDecision, Draft, Preset, PublishLog, PublishTask
from publishers.base import PublishPayload, PublishResult
from publishers.registry import get_adapter

router = APIRouter(tags=["publish"])
settings = get_settings()
scheduler_timezone = ZoneInfo(settings.schedule_timezone)


class PublishRequest(BaseModel):
    draft_id: int
    account_id: int
    preset_id: str = "fresh"
    authorized: bool = False
    ad_acknowledged: bool = False
    scheduled_at: datetime | None = None
    max_retries: int = Field(default=1, ge=0, le=3)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=120)


def serialize_task(task: PublishTask, db: Session) -> dict:
    draft = db.get(Draft, task.draft_id)
    logs = db.scalars(
        select(PublishLog).where(PublishLog.task_id == task.id).order_by(PublishLog.created_at)
    ).all()
    return {
        "id": task.id,
        "draft_id": task.draft_id,
        "draft_title": json.loads(task.snapshot_json)["title"]
        if task.snapshot_json
        else (draft.title if draft else "草稿已删除"),
        "account_id": task.account_id,
        "platform": task.platform,
        "content_type": task.content_type,
        "preset_id": task.preset_id,
        "status": task.status,
        "result_url": sanitize_url(task.result_url) if task.result_url else None,
        "error_msg": sanitize_text(task.error_msg) if task.error_msg else None,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "next_retry_at": task.next_retry_at.isoformat() if task.next_retry_at else None,
        "scheduled_at": task.scheduled_at.isoformat() if task.scheduled_at else None,
        "schedule_plan_id": task.schedule_plan_id,
        "submission_uncertain": task.submission_uncertain,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "logs": [
            {
                "level": row.level,
                "message": sanitize_text(row.message, 2000),
                "created_at": row.created_at.isoformat(),
            }
            for row in logs
        ],
    }


def prepare_draft_content(
    draft: Draft,
    preset: Preset,
    db: Session,
) -> tuple[list[dict], str, str, VideoMetadata | None, str]:
    metadata = None
    rendered = ""
    media_sha256 = ""
    if draft.content_type == "video":
        metadata = validate_video(draft.video_path or "")
        media_path = settings.data_dir / metadata.video_path
        media_sha256 = f"video:{file_sha256(media_path)}"
        compliance_body = draft.body
        media_metadata = {
            **metadata.to_dict(),
            "partition": draft.video_partition,
            "collection": draft.video_collection,
        }
    else:
        rendered = render_article(
            draft.title,
            draft.body,
            preset.id,
            draft.cover_image,
            resolve_preset(preset.id, db),
        )
        compliance_body = plain_text_from_html(rendered)
        media_metadata = {"cover_url": draft.cover_image}
    if draft.cover_image and draft.cover_image.startswith("/media/"):
        cover_path = settings.data_dir / "covers" / Path(draft.cover_image).name
        if cover_path.is_file():
            cover_hash = f"cover:{file_sha256(cover_path)}"
            media_sha256 = f"{media_sha256}|{cover_hash}" if media_sha256 else cover_hash
    findings = validate_content(
        draft.title,
        compliance_body,
        settings.compliance_enabled,
        draft.tags,
    )
    fingerprint = content_fingerprint(
        draft.title,
        draft.body,
        draft.tags,
        rendered_html=rendered,
        media_sha256=media_sha256,
        media_metadata=media_metadata,
    )
    return findings, fingerprint, rendered, metadata, media_sha256


def create_publish_snapshot(draft: Draft, preset: Preset, db: Session) -> tuple[dict, list[dict]]:
    findings, fingerprint, rendered, metadata, media_sha256 = prepare_draft_content(
        draft, preset, db
    )
    snapshot = {
        "title": draft.title,
        "body": draft.body,
        "tags": draft.tags,
        "content_type": draft.content_type,
        "cover_image": draft.cover_image,
        "video_path": metadata.video_path if metadata else None,
        "rendered_html": rendered,
        "media_sha256": media_sha256,
        "media_metadata": (
            {
                **metadata.to_dict(),
                "partition": draft.video_partition,
                "collection": draft.video_collection,
            }
            if metadata
            else {"cover_url": draft.cover_image}
        ),
        "content_sha256": fingerprint,
    }
    return snapshot, findings


def validate_publish_snapshot(snapshot: dict) -> tuple[list[dict], str, VideoMetadata | None]:
    required = {
        "title",
        "body",
        "tags",
        "content_type",
        "rendered_html",
        "media_metadata",
        "content_sha256",
    }
    if not required.issubset(snapshot):
        raise ValueError("发布快照不完整。")
    metadata = None
    media_sha256 = ""
    if snapshot["content_type"] == "video":
        metadata = validate_video(snapshot.get("video_path") or "")
        media_path = settings.data_dir / metadata.video_path
        media_sha256 = f"video:{file_sha256(media_path)}"
        compliance_body = snapshot["body"]
    else:
        compliance_body = plain_text_from_html(snapshot["rendered_html"])
    cover_image = snapshot.get("cover_image")
    if cover_image and cover_image.startswith("/media/"):
        cover_path = settings.data_dir / "covers" / Path(cover_image).name
        if cover_path.is_file():
            cover_hash = f"cover:{file_sha256(cover_path)}"
            media_sha256 = f"{media_sha256}|{cover_hash}" if media_sha256 else cover_hash
    fingerprint = content_fingerprint(
        snapshot["title"],
        snapshot["body"],
        snapshot["tags"],
        rendered_html=snapshot["rendered_html"],
        media_sha256=media_sha256,
        media_metadata=snapshot["media_metadata"],
    )
    if fingerprint != snapshot["content_sha256"]:
        raise ValueError("发布快照对应的媒体或内容已发生变化。")
    findings = validate_content(
        snapshot["title"],
        compliance_body,
        settings.compliance_enabled,
        snapshot["tags"],
    )
    return findings, fingerprint, metadata


def record_compliance_decision(
    db: Session,
    task: PublishTask,
    findings: list[dict],
    *,
    fingerprint: str,
    ad_acknowledged: bool,
    passed: bool,
) -> ComplianceDecision:
    decision = ComplianceDecision(
        task_id=task.id,
        content_sha256=fingerprint,
        ruleset_version=settings.compliance_ruleset_version,
        passed=passed,
        findings_json=json.dumps(findings, ensure_ascii=False),
        ad_acknowledged=ad_acknowledged,
    )
    db.add(decision)
    return decision


def run_publish(task_id: int) -> None:
    with SessionLocal.begin() as db:
        task = db.get(PublishTask, task_id)
        if not task or task.status != "pending":
            return
        if not settings.publishing_enabled:
            task.status = "failed"
            task.error_msg = "当前运行模式已禁用真实发布，请在带可见浏览器的本机模式重试。"
            db.add(PublishLog(task_id=task_id, level="error", message=task.error_msg))
            add_audit_event(
                db,
                action="publish.execute",
                entity_type="publish_task",
                entity_id=task_id,
                outcome="denied",
                message=task.error_msg,
            )
            return
        task.status = "running"
        draft = db.get(Draft, task.draft_id)
        account = db.get(Account, task.account_id)
        preset = db.get(Preset, task.preset_id)
        if not draft or not account or not preset:
            task.status = "failed"
            task.error_msg = "草稿、账号或预设不存在。"
            db.add(PublishLog(task_id=task_id, level="error", message=task.error_msg))
            add_audit_event(
                db,
                action="publish.execute",
                entity_type="publish_task",
                entity_id=task_id,
                outcome="denied",
                message=task.error_msg,
            )
            return
        options = None
        try:
            adapter = get_adapter(account.platform)
            cookies = json.loads(CredentialVault().decrypt(account.cookie_encrypted))
            if task.snapshot_json:
                snapshot = json.loads(task.snapshot_json)
            elif draft and preset:
                snapshot, _ = create_publish_snapshot(draft, preset, db)
                task.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
            else:
                raise ValueError("发布快照不存在。")
            findings, fingerprint, metadata = validate_publish_snapshot(snapshot)
            cover_path = None
            if snapshot.get("cover_image") and snapshot["cover_image"].startswith("/media/"):
                cover_path = settings.data_dir / "covers" / Path(snapshot["cover_image"]).name
            if snapshot["content_type"] == "video":
                if "video" not in adapter.content_types:
                    raise ValueError("该平台账号不支持视频发布。")
                options = {
                    "partition": snapshot["media_metadata"].get("partition"),
                    "collection": snapshot["media_metadata"].get("collection"),
                }
            payload = PublishPayload(
                title=snapshot["title"],
                body=snapshot["body"],
                rendered_html=snapshot["rendered_html"],
                tags=[tag for tag in snapshot["tags"].split(",") if tag],
                cover_path=cover_path,
                video_path=None,
                video_duration=metadata.duration if metadata else None,
                video_width=metadata.width if metadata else None,
                video_height=metadata.height if metadata else None,
            )
            if metadata:
                payload.video_path = settings.data_dir / metadata.video_path
        except VideoError as exc:
            task.status = "failed"
            task.error_msg = sanitize_text(f"视频校验失败：{exc}", 2000)
            db.add(PublishLog(task_id=task_id, level="error", message=task.error_msg))
            add_audit_event(
                db,
                action="publish.prepare",
                entity_type="publish_task",
                entity_id=task_id,
                outcome="denied",
                message=task.error_msg,
            )
            draft.status = "draft"
            return
        except ValueError as exc:
            task.status = "failed"
            task.error_msg = sanitize_text(f"发布快照校验失败：{exc}", 2000)
            db.add(PublishLog(task_id=task_id, level="error", message=task.error_msg))
            add_audit_event(
                db,
                action="publish.prepare",
                entity_type="publish_task",
                entity_id=task_id,
                outcome="denied",
                message=task.error_msg,
            )
            draft.status = "draft"
            return
        except Exception as exc:
            task.status = "failed"
            task.error_msg = sanitize_text(
                f"发布准备失败：{type(exc).__name__}。请检查账号凭证、视频与封面文件。", 2000
            )
            db.add(PublishLog(task_id=task_id, level="error", message=task.error_msg))
            add_audit_event(
                db,
                action="publish.prepare",
                entity_type="publish_task",
                entity_id=task_id,
                outcome="error",
                message=task.error_msg,
            )
            draft.status = "draft"
            return
        previous_decision = db.scalar(
            select(ComplianceDecision)
            .where(ComplianceDecision.task_id == task_id)
            .order_by(ComplianceDecision.created_at.desc(), ComplianceDecision.id.desc())
        )
        ad_acknowledged = bool(
            previous_decision
            and previous_decision.content_sha256 == fingerprint
            and previous_decision.ad_acknowledged
        )
        blocked = any(item["type"] == "prohibited" for item in findings) or (
            any(item["type"] == "advertising" for item in findings) and not ad_acknowledged
        )
        record_compliance_decision(
            db,
            task,
            findings,
            fingerprint=fingerprint,
            ad_acknowledged=ad_acknowledged,
            passed=not blocked,
        )
        if blocked:
            task.status = "failed"
            task.error_msg = "执行前合规校验未通过，任务已停止且不会自动重试。"
            draft.status = "draft"
            db.add(PublishLog(task_id=task_id, level="error", message=task.error_msg))
            add_audit_event(
                db,
                action="publish.compliance",
                entity_type="publish_task",
                entity_id=task_id,
                outcome="denied",
                message=task.error_msg,
                metadata={"content_sha256": fingerprint, "findings": findings},
            )
            return
        add_audit_event(
            db,
            action="publish.compliance",
            entity_type="publish_task",
            entity_id=task_id,
            outcome="success",
            message="执行前合规复验通过",
            metadata={
                "content_sha256": fingerprint,
                "ruleset_version": settings.compliance_ruleset_version,
            },
        )
        account_id = account.id
    log_task_event(task_id, "info", f"开始连接 {adapter.display_name} 发布页面。")
    try:
        result = (
            adapter.publish(payload, cookies, options)
            if options is not None
            else adapter.publish(payload, cookies)
        )
    except Exception as exc:
        result = PublishResult(
            False,
            message=f"发布服务异常，结果不确定：{type(exc).__name__}。请先在平台确认。",
            requires_manual=True,
            uncertain=True,
        )
    retry_scheduled = False
    with SessionLocal.begin() as db:
        task = db.get(PublishTask, task_id)
        draft = db.get(Draft, task.draft_id)
        account = db.get(Account, account_id)
        if result.success:
            task.status = "success"
            task.result_url = sanitize_url(result.url) if result.url else None
            task.error_msg = None
            task.submission_uncertain = False
            preset = db.get(Preset, task.preset_id)
            if (
                draft
                and preset
                and draft.updated_at <= task.created_at
                and (preset.updated_at or datetime.min) <= task.created_at
            ):
                draft.status = "published"
            account.login_valid = True
            db.add(PublishLog(task_id=task_id, level="info", message="平台已返回发布成功回执。"))
        else:
            task.error_msg = sanitize_text(result.message, 2000)
            task.submission_uncertain = result.uncertain
            if draft and draft.status != "published":
                draft.status = "draft"
            if "登录态" in result.message:
                account.login_valid = False
            if result.retryable and not result.uncertain and task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = "pending"
                task.next_retry_at = datetime.now(scheduler_timezone).replace(
                    tzinfo=None
                ) + timedelta(seconds=settings.retry_delay_seconds)
                retry_scheduled = True
                db.add(
                    PublishLog(
                        task_id=task_id,
                        level="info",
                        message=f"失败可安全重试，已安排第 {task.retry_count} 次自动重试。",
                    )
                )
            else:
                task.status = "failed"
                db.add(
                    PublishLog(
                        task_id=task_id, level="error", message=sanitize_text(result.message, 2000)
                    )
                )
        add_audit_event(
            db,
            action="publish.result",
            entity_type="publish_task",
            entity_id=task_id,
            outcome="success" if result.success else "error",
            message="平台已返回发布成功回执。" if result.success else result.message,
            metadata={"retry_scheduled": retry_scheduled, "result_url": result.url},
        )
    if retry_scheduled:
        queue_manager.enqueue(task_id)


@router.post("/publish", status_code=202)
def publish(request: PublishRequest, db: Session = Depends(get_db)):
    if not settings.publishing_enabled:
        raise HTTPException(503, "当前运行模式已禁用真实发布，请在带可见浏览器的本机模式使用。")
    draft = db.get(Draft, request.draft_id)
    account = db.get(Account, request.account_id)
    preset = db.get(Preset, request.preset_id)
    if not draft or not account or not preset:
        raise HTTPException(404, "草稿、账号或排版预设不存在。")
    try:
        adapter = get_adapter(account.platform)
    except (ImportError, ValueError) as exc:
        raise HTTPException(400, f"暂不支持平台：{account.platform}") from exc
    if draft.content_type not in adapter.content_types:
        raise HTTPException(400, "该账号平台不支持此内容类型。")
    if not draft.title.strip():
        raise HTTPException(400, "标题不能为空。")
    if draft.content_type == "video":
        if not draft.video_path:
            raise HTTPException(400, "请先上传并校验视频。")
        if adapter.title_limit and len(draft.title) > adapter.title_limit:
            raise HTTPException(400, f"标题不能超过 {adapter.title_limit} 个字符。")
    elif not draft.body.strip():
        raise HTTPException(400, "正文不能为空。")
    if not request.authorized:
        raise HTTPException(400, "请确认内容归属与平台自动化授权。")
    if request.idempotency_key:
        existing = db.scalar(
            select(PublishTask).where(PublishTask.idempotency_key == request.idempotency_key)
        )
        if existing:
            if existing.draft_id != draft.id or existing.account_id != account.id:
                raise HTTPException(409, "幂等键已用于其他发布任务。")
            return serialize_task(existing, db)
    scheduled_at = request.scheduled_at
    if scheduled_at:
        scheduled_at = (
            scheduled_at.astimezone(scheduler_timezone).replace(tzinfo=None)
            if scheduled_at.tzinfo
            else scheduled_at
        )
        now = datetime.now(scheduler_timezone).replace(tzinfo=None)
        if scheduled_at <= now + timedelta(seconds=5):
            raise HTTPException(400, "定时时间至少需要晚于当前时间 5 秒。")
        if scheduled_at > now + timedelta(days=366):
            raise HTTPException(400, "定时时间不能超过一年。")
    try:
        snapshot, findings = create_publish_snapshot(draft, preset, db)
        fingerprint = snapshot["content_sha256"]
    except VideoError as exc:
        raise HTTPException(400, str(exc)) from exc
    if any(item["type"] == "prohibited" for item in findings):
        raise HTTPException(400, "内容包含禁止发布项，已拦截。")
    ads = [item for item in findings if item["type"] == "advertising"]
    if ads and not request.ad_acknowledged:
        raise HTTPException(400, "检测到广告法风险用语，请修改内容或确认已知悉风险。")
    duplicate = db.scalar(
        select(PublishTask.id).where(
            PublishTask.draft_id == draft.id,
            PublishTask.account_id == account.id,
            PublishTask.status.in_(["pending", "running"]),
        )
    )
    if duplicate:
        raise HTTPException(409, "相同草稿和账号已有等待中的任务，请勿重复提交。")

    task = PublishTask(
        draft_id=draft.id,
        account_id=account.id,
        platform=account.platform,
        content_type=draft.content_type,
        preset_id=preset.id,
        status="pending",
        scheduled_at=scheduled_at,
        max_retries=request.max_retries,
        idempotency_key=request.idempotency_key,
        snapshot_json=json.dumps(snapshot, ensure_ascii=False),
    )
    db.add(task)
    db.flush()
    record_compliance_decision(
        db,
        task,
        findings,
        fingerprint=fingerprint,
        ad_acknowledged=request.ad_acknowledged,
        passed=True,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if request.idempotency_key:
            existing = db.scalar(
                select(PublishTask).where(PublishTask.idempotency_key == request.idempotency_key)
            )
            if existing:
                return serialize_task(existing, db)
        raise HTTPException(409, "相同草稿和账号已有等待中的任务，请勿重复提交。") from exc
    db.refresh(task)
    timing = "定时" if scheduled_at else "立即"
    log_task_event(
        task.id, "info", f"用户确认内容归属与平台授权，创建{adapter.display_name}{timing}发布任务。"
    )
    queue_manager.enqueue(task.id)
    return serialize_task(task, db)


@router.post("/tasks/{task_id}/retry", status_code=202)
def retry_task(task_id: int, db: Session = Depends(get_db)):
    if not settings.publishing_enabled:
        raise HTTPException(503, "当前运行模式已禁用真实发布，请在带可见浏览器的本机模式重试。")
    task = db.get(PublishTask, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status in {"pending", "running"}:
        raise HTTPException(409, "任务正在处理中，不能重复提交。")
    if task.status != "failed":
        raise HTTPException(409, "只有失败任务可以手动重试。")
    uncertain_markers = ("未收到平台成功回执", "验证", "结果不确定")
    if task.submission_uncertain or any(
        marker in (task.error_msg or "") for marker in uncertain_markers
    ):
        raise HTTPException(409, "上次结果不确定，请先在平台确认文章状态，避免重复发布。")
    task.status = "pending"
    task.error_msg = None
    task.submission_uncertain = False
    task.next_retry_at = None
    task.retry_count += 1
    db.commit()
    log_task_event(task.id, "info", f"用户手动重试，第 {task.retry_count} 次。")
    queue_manager.enqueue(task.id)
    db.refresh(task)
    return serialize_task(task, db)


@router.post("/tasks/{task_id}/pause", status_code=202)
def pause_task(task_id: int, db: Session = Depends(get_db)):
    try:
        queue_manager.pause(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return serialize_task(db.get(PublishTask, task_id), db)


@router.post("/tasks/{task_id}/resume", status_code=202)
def resume_task(task_id: int, db: Session = Depends(get_db)):
    try:
        queue_manager.resume(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return serialize_task(db.get(PublishTask, task_id), db)


@router.post("/tasks/{task_id}/skip", status_code=202)
def skip_task(task_id: int, db: Session = Depends(get_db)):
    try:
        queue_manager.skip(task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return serialize_task(db.get(PublishTask, task_id), db)
