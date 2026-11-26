import importlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.publish import create_publish_snapshot
from app.api.schedules import create_plan_tasks
from app.auth.credentials import CredentialVault
from app.config import get_settings
from app.main import app
from app.queue_scheduler.manager import QueueManager
from app.storage.database import SessionLocal
from app.storage.models import (
    Account,
    AuditEvent,
    Draft,
    Preset,
    PublishLog,
    PublishTask,
    SchedulePlan,
)
from publishers.base import PublishResult
from publishers.bilibili.adapter import SELECTORS_PATH


def create_account(db: Session, platform: str = "csdn") -> Account:
    account = Account(
        platform=platform,
        nickname=f"阶段2测试-{platform}",
        cookie_encrypted=CredentialVault().encrypt('[{"name":"session","value":"test"}]'),
    )
    db.add(account)
    db.flush()
    return account


def create_draft(db: Session) -> Draft:
    draft = Draft(title="阶段2调度测试", body="用于验证本地调度与安全重试。", tags="测试")
    db.add(draft)
    db.flush()
    return draft


def cleanup_task(db, task: PublishTask) -> None:
    for log in db.scalars(select(PublishLog).where(PublishLog.task_id == task.id)).all():
        db.delete(log)
    db.delete(task)


def test_scheduled_publish_timezone_and_queue_controls():
    timezone = ZoneInfo(get_settings().schedule_timezone)
    with SessionLocal() as db:
        account = create_account(db)
        draft = create_draft(db)
        db.commit()
        account_id, draft_id = account.id, draft.id

    try:
        with TestClient(app) as client:
            scheduled = datetime.now(timezone) + timedelta(hours=1)
            response = client.post(
                "/api/publish",
                json={
                    "draft_id": draft_id,
                    "account_id": account_id,
                    "preset_id": "fresh",
                    "authorized": True,
                    "scheduled_at": scheduled.isoformat(),
                    "max_retries": 2,
                },
            )
            assert response.status_code == 202, response.text
            payload = response.json()
            assert payload["status"] == "pending"
            assert payload["max_retries"] == 2
            stored = datetime.fromisoformat(payload["scheduled_at"])
            assert abs((stored - scheduled.replace(tzinfo=None)).total_seconds()) < 2
            task_id = payload["id"]

            assert client.post(f"/api/tasks/{task_id}/pause").json()["status"] == "paused"
            assert client.post(f"/api/tasks/{task_id}/resume").json()["status"] == "pending"
            assert client.post(f"/api/tasks/{task_id}/skip").json()["status"] == "skipped"
            assert client.post(f"/api/tasks/{task_id}/pause").status_code == 409
    finally:
        with SessionLocal.begin() as db:
            for task in db.scalars(
                select(PublishTask).where(
                    PublishTask.draft_id == draft_id, PublishTask.account_id == account_id
                )
            ).all():
                cleanup_task(db, task)
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


def test_schedule_run_is_idempotent_and_staggered(monkeypatch):
    interval = get_settings().min_publish_interval_seconds
    with SessionLocal() as db:
        first = create_account(db)
        second = create_account(db, "zhihu")
        draft = create_draft(db)
        plan = SchedulePlan(
            name="幂等与错峰测试",
            draft_id=draft.id,
            account_ids=json.dumps([first.id, second.id]),
            preset_id="fresh",
            cron_expr="30 9 * * *",
            enabled=True,
            authorized=True,
        )
        snapshot, _ = create_publish_snapshot(draft, db.get(Preset, "fresh"), db)
        plan.authorized_fingerprint = snapshot["content_sha256"]
        db.add(plan)
        db.commit()
        first_id, second_id, draft_id, plan_id = first.id, second.id, draft.id, plan.id

    monkeypatch.setattr("app.api.schedules.queue_manager.enqueue", lambda task_id: None)
    try:
        first_run = create_plan_tasks(plan_id, "202611260900")
        duplicate_run = create_plan_tasks(plan_id, "202611260900")
        assert len(first_run) == 2
        assert duplicate_run == []
        with SessionLocal() as db:
            tasks = db.scalars(
                select(PublishTask)
                .where(PublishTask.schedule_plan_id == plan_id)
                .order_by(PublishTask.account_id)
            ).all()
            assert len(tasks) == 2
            gap = (tasks[1].scheduled_at - tasks[0].scheduled_at).total_seconds()
            assert gap >= interval
    finally:
        with SessionLocal.begin() as db:
            for task in db.scalars(
                select(PublishTask).where(PublishTask.schedule_plan_id == plan_id)
            ).all():
                cleanup_task(db, task)
            db.delete(db.get(SchedulePlan, plan_id))
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, first_id))
            db.delete(db.get(Account, second_id))


def test_one_time_plan_is_consumed_atomically_and_idempotent(monkeypatch):
    with SessionLocal() as db:
        account = create_account(db)
        draft = create_draft(db)
        scheduled_at = datetime.now() + timedelta(hours=2)
        plan = SchedulePlan(
            name="一次性计划原子消费测试",
            draft_id=draft.id,
            account_ids=json.dumps([account.id]),
            preset_id="fresh",
            scheduled_at=scheduled_at,
            enabled=True,
            authorized=True,
        )
        snapshot, _ = create_publish_snapshot(draft, db.get(Preset, "fresh"), db)
        plan.authorized_fingerprint = snapshot["content_sha256"]
        db.add(plan)
        db.commit()
        account_id, draft_id, plan_id = account.id, draft.id, plan.id

    monkeypatch.setattr("app.api.schedules.queue_manager.enqueue", lambda task_id: None)
    try:
        assert len(create_plan_tasks(plan_id, "202611261100")) == 1
        assert create_plan_tasks(plan_id, "202611261101") == []
        with SessionLocal() as db:
            stored = db.get(SchedulePlan, plan_id)
            task = db.scalar(select(PublishTask).where(PublishTask.schedule_plan_id == plan_id))
            assert stored.enabled is False
            assert stored.next_run_at is None
            assert (
                task.run_key == f"plan-{plan_id}:{scheduled_at.strftime('%Y%m%d%H%M')}:{account_id}"
            )
    finally:
        with SessionLocal.begin() as db:
            for task in db.scalars(
                select(PublishTask).where(PublishTask.schedule_plan_id == plan_id)
            ).all():
                cleanup_task(db, task)
            db.delete(db.get(SchedulePlan, plan_id))
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


def test_changed_content_disables_plan_and_account_deletion_protects_references(monkeypatch):
    with SessionLocal.begin() as db:
        account = create_account(db)
        draft = create_draft(db)
        snapshot, _ = create_publish_snapshot(draft, db.get(Preset, "fresh"), db)
        plan = SchedulePlan(
            name="授权失效测试",
            draft_id=draft.id,
            account_ids=json.dumps([account.id]),
            preset_id="fresh",
            cron_expr="30 9 * * *",
            enabled=True,
            authorized=True,
            authorized_fingerprint=snapshot["content_sha256"],
        )
        db.add(plan)
        db.commit()
        account_id, draft_id, plan_id = account.id, draft.id, plan.id

    monkeypatch.setattr("app.api.schedules.queue_manager.enqueue", lambda task_id: None)
    try:
        with SessionLocal.begin() as db:
            db.get(Draft, draft_id).body = "授权之后再次修改的正文"
        with TestClient(app) as client:
            plans = client.get("/api/schedules").json()
            stored_plan = next(item for item in plans if item["id"] == plan_id)
            assert stored_plan["authorization_valid"] is False
            enabled = client.patch(f"/api/schedules/{plan_id}", json={"enabled": True})
            assert enabled.status_code == 409
            deleted = client.delete(f"/api/accounts/{account_id}")
            assert deleted.status_code == 409
            assert "调度计划" in deleted.json()["detail"]
        assert create_plan_tasks(plan_id, "202611260900") == []
        with SessionLocal() as db:
            assert db.get(SchedulePlan, plan_id).enabled is False
    finally:
        with SessionLocal.begin() as db:
            db.execute(
                delete(AuditEvent).where(
                    AuditEvent.entity_type == "schedule_plan", AuditEvent.entity_id == plan_id
                )
            )
            db.delete(db.get(SchedulePlan, plan_id))
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


def test_restart_does_not_catch_up_expired_one_time_plan():
    class Scheduler:
        running = True

        def __init__(self):
            self.added = []
            self.removed = []

        def get_job(self, job_id):
            return None

        def remove_job(self, job_id):
            self.removed.append(job_id)

        def add_job(self, *args, **kwargs):
            self.added.append((args, kwargs))

    manager = QueueManager()
    manager.scheduler = Scheduler()
    with SessionLocal() as db:
        draft = create_draft(db)
        plan = SchedulePlan(
            name="过期计划不补发测试",
            draft_id=draft.id,
            account_ids="[]",
            preset_id="fresh",
            scheduled_at=datetime.now() - timedelta(minutes=10),
            enabled=True,
            authorized=True,
        )
        db.add(plan)
        db.commit()
        draft_id, plan_id = draft.id, plan.id
    try:
        manager.register_plan(plan_id)
        with SessionLocal() as db:
            stored = db.get(SchedulePlan, plan_id)
            assert stored.enabled is False
            assert stored.next_run_at is None
        assert manager.scheduler.added == []
    finally:
        with SessionLocal.begin() as db:
            db.delete(db.get(SchedulePlan, plan_id))
            db.delete(db.get(Draft, draft_id))


@pytest.mark.parametrize("cron", ["30 9 * * *", None])
def test_recurring_plan_keeps_job_and_one_time_plan_removes_it(monkeypatch, cron):
    class Scheduler:
        def __init__(self):
            self.removed = []

        def get_job(self, job_id):
            return type("Job", (), {"id": job_id})()

        def remove_job(self, job_id):
            self.removed.append(job_id)

    manager = QueueManager()
    manager.scheduler = Scheduler()
    with SessionLocal() as db:
        draft = create_draft(db)
        plan = SchedulePlan(
            name="周期任务保留测试",
            draft_id=draft.id,
            account_ids="[]",
            preset_id="fresh",
            cron_expr=cron,
            scheduled_at=datetime.now() + timedelta(hours=1) if not cron else None,
            enabled=True,
            authorized=True,
        )
        db.add(plan)
        db.commit()
        draft_id, plan_id = draft.id, plan.id

    monkeypatch.setattr("app.api.schedules.create_plan_tasks", lambda plan_id, slot: [])
    try:
        manager._run_plan(plan_id)
        assert manager.scheduler.removed == ([] if cron else [f"plan-{plan_id}"])
    finally:
        with SessionLocal.begin() as db:
            db.delete(db.get(SchedulePlan, plan_id))
            db.delete(db.get(Draft, draft_id))


def test_restart_marks_interrupted_task_for_manual_confirmation():
    manager = QueueManager()
    with SessionLocal() as db:
        account = create_account(db)
        draft = create_draft(db)
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
            status="running",
        )
        db.add(task)
        db.commit()
        task_id, draft_id, account_id = task.id, draft.id, account.id
    try:
        manager._restore_tasks()
        with SessionLocal() as db:
            restored = db.get(PublishTask, task_id)
            assert restored.status == "failed"
            assert restored.submission_uncertain is True
            assert "结果不确定" in restored.error_msg
            assert any("服务中断" in log.message for log in restored.logs)
    finally:
        with SessionLocal.begin() as db:
            task = db.get(PublishTask, task_id)
            if task:
                cleanup_task(db, task)
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


def test_disabled_queue_disables_existing_work_without_execution(monkeypatch):
    import yaml

    schedules_module = importlib.import_module("app.api.schedules")
    manager = QueueManager()
    monkeypatch.setattr(manager.settings, "publishing_enabled", False)
    monkeypatch.setattr(schedules_module.settings, "publishing_enabled", False)
    monkeypatch.setattr(manager, "enqueue", lambda task_id: pytest.fail("禁用模式不应入队"))
    with SessionLocal.begin() as db:
        account = create_account(db)
        draft = create_draft(db)
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
        )
        plan = SchedulePlan(
            name="禁用模式计划",
            draft_id=draft.id,
            account_ids=json.dumps([account.id]),
            preset_id="fresh",
            cron_expr="30 9 * * *",
            enabled=True,
            authorized=True,
        )
        db.add_all([task, plan])
        db.commit()
        task_id, plan_id, draft_id, account_id = task.id, plan.id, draft.id, account.id
    try:
        manager._disable_publishing()
        assert create_plan_tasks(plan_id, "202611260900") == []
        with SessionLocal() as db:
            assert db.get(PublishTask, task_id).status == "failed"
            assert db.get(PublishTask, task_id).submission_uncertain is False
            assert db.get(SchedulePlan, plan_id).enabled is False
        selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
        assert "text=重新上传" not in selectors["upload_success_selectors"]
    finally:
        with SessionLocal.begin() as db:
            db.execute(
                delete(AuditEvent).where(
                    AuditEvent.entity_type == "publish_task", AuditEvent.entity_id == task_id
                )
            )
            db.execute(
                delete(AuditEvent).where(
                    AuditEvent.entity_type == "schedule_plan", AuditEvent.entity_id == plan_id
                )
            )
            cleanup_task(db, db.get(PublishTask, task_id))
            db.delete(db.get(SchedulePlan, plan_id))
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


@pytest.mark.parametrize(
    ("retryable", "expected_status", "expected_enqueue"),
    [(True, "pending", 1), (False, "failed", 0)],
)
def test_worker_retries_only_explicitly_retryable_results(
    monkeypatch, retryable, expected_status, expected_enqueue
):
    class FakeAdapter:
        display_name = "测试平台"

        def publish(self, payload, cookies, options=None):
            return PublishResult(False, message="临时服务异常", retryable=retryable)

    publish_module = importlib.import_module("app.api.publish")
    monkeypatch.setattr(publish_module, "get_adapter", lambda platform: FakeAdapter())
    enqueued = []
    monkeypatch.setattr(
        publish_module.queue_manager, "enqueue", lambda task_id: enqueued.append(task_id)
    )
    with SessionLocal() as db:
        account = create_account(db)
        draft = create_draft(db)
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
            status="pending",
            max_retries=1,
        )
        db.add(task)
        db.commit()
        task_id, draft_id, account_id = task.id, draft.id, account.id
    try:
        publish_module.run_publish(task_id)
        with SessionLocal() as db:
            result = db.get(PublishTask, task_id)
            assert result.status == expected_status
            assert result.retry_count == expected_enqueue
            assert len(enqueued) == expected_enqueue
            if retryable:
                assert result.next_retry_at is not None
    finally:
        with SessionLocal.begin() as db:
            task = db.get(PublishTask, task_id)
            if task:
                cleanup_task(db, task)
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))
