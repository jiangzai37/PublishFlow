from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import get_settings
from app.storage.audit import add_audit_event
from app.storage.database import SessionLocal
from app.storage.models import PublishLog, PublishTask, SchedulePlan


class QueueManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.timezone = ZoneInfo(self.settings.schedule_timezone)
        self.scheduler = BackgroundScheduler(
            timezone=self.timezone,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )

    def start(self) -> None:
        if self.scheduler.running:
            return
        self.scheduler.start()
        if not self.settings.publishing_enabled:
            self._disable_publishing()
            return
        self._restore_tasks()
        self._restore_plans()
        self.scheduler.add_job(
            self.reconcile, "interval", seconds=30, id="queue-reconcile", replace_existing=True
        )

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _disable_publishing(self) -> None:
        with SessionLocal.begin() as db:
            for task in db.scalars(
                select(PublishTask).where(PublishTask.status.in_(["pending", "running"]))
            ).all():
                interrupted = task.status == "running"
                task.status = "failed"
                task.submission_uncertain = interrupted
                task.error_msg = (
                    "服务中断导致发布结果不确定，请先在平台确认，勿直接重复发布。"
                    if interrupted
                    else "当前运行模式已禁用真实发布，任务未执行。"
                )
                db.add(PublishLog(task_id=task.id, level="error", message=task.error_msg))
                add_audit_event(
                    db,
                    action="queue.recover",
                    entity_type="publish_task",
                    entity_id=task.id,
                    outcome="denied",
                    message=task.error_msg,
                )
            for plan in db.scalars(
                select(SchedulePlan).where(SchedulePlan.enabled.is_(True))
            ).all():
                plan.enabled = False
                plan.next_run_at = None
                add_audit_event(
                    db,
                    action="schedule.authorization",
                    entity_type="schedule_plan",
                    entity_id=plan.id,
                    outcome="denied",
                    message="当前运行模式已禁用真实发布，计划已停用。",
                )

    def _restore_tasks(self) -> None:
        with SessionLocal.begin() as db:
            interrupted = db.scalars(
                select(PublishTask).where(PublishTask.status == "running")
            ).all()
            for task in interrupted:
                task.status = "failed"
                task.submission_uncertain = True
                task.error_msg = "服务中断导致发布结果不确定，请先在平台确认，勿直接重复发布。"
                db.add(PublishLog(task_id=task.id, level="error", message=task.error_msg))
                add_audit_event(
                    db,
                    action="queue.recover",
                    entity_type="publish_task",
                    entity_id=task.id,
                    outcome="error",
                    message=task.error_msg,
                )
            pending_ids = [
                task.id
                for task in db.scalars(
                    select(PublishTask).where(PublishTask.status == "pending")
                ).all()
            ]
        for task_id in pending_ids:
            self.enqueue(task_id)

    def _restore_plans(self) -> None:
        with SessionLocal() as db:
            plan_ids = [
                plan.id
                for plan in db.scalars(
                    select(SchedulePlan).where(SchedulePlan.enabled.is_(True))
                ).all()
            ]
        for plan_id in plan_ids:
            self.register_plan(plan_id)

    def enqueue(self, task_id: int) -> None:
        if not self.settings.publishing_enabled or not self.scheduler.running:
            return
        with SessionLocal() as db:
            task = db.get(PublishTask, task_id)
            if not task or task.status != "pending":
                return
            now = datetime.now(self.timezone).replace(tzinfo=None)
            candidates = [value for value in (task.next_retry_at, task.scheduled_at) if value]
            run_at = max([now, *candidates])
        self.scheduler.add_job(
            self._execute,
            "date",
            run_date=run_at,
            id=f"task-{task_id}",
            args=[task_id],
            replace_existing=True,
        )

    def _execute(self, task_id: int) -> None:
        from app.api.publish import run_publish

        run_publish(task_id)

    def pause(self, task_id: int) -> PublishTask:
        with SessionLocal.begin() as db:
            task = db.get(PublishTask, task_id)
            if not task:
                raise ValueError("任务不存在")
            if task.status != "pending":
                raise ValueError("只有等待中的任务可以暂停")
            task.status = "paused"
            db.add(PublishLog(task_id=task.id, level="info", message="用户暂停了等待中的任务。"))
            add_audit_event(
                db,
                action="queue.pause",
                entity_type="publish_task",
                entity_id=task.id,
                outcome="success",
                message="用户暂停了等待中的任务。",
            )
        job = self.scheduler.get_job(f"task-{task_id}")
        if job:
            self.scheduler.remove_job(job.id)
        with SessionLocal() as db:
            return db.get(PublishTask, task_id)

    def resume(self, task_id: int) -> PublishTask:
        with SessionLocal.begin() as db:
            task = db.get(PublishTask, task_id)
            if not task:
                raise ValueError("任务不存在")
            if task.status != "paused":
                raise ValueError("只有已暂停的任务可以恢复")
            if not self.settings.publishing_enabled:
                raise ValueError("当前运行模式已禁用真实发布")
            task.status = "pending"
            db.add(PublishLog(task_id=task.id, level="info", message="用户恢复了发布任务。"))
            add_audit_event(
                db,
                action="queue.resume",
                entity_type="publish_task",
                entity_id=task.id,
                outcome="success",
                message="用户恢复了发布任务。",
            )
        self.enqueue(task_id)
        with SessionLocal() as db:
            return db.get(PublishTask, task_id)

    def skip(self, task_id: int) -> PublishTask:
        with SessionLocal.begin() as db:
            task = db.get(PublishTask, task_id)
            if not task:
                raise ValueError("任务不存在")
            if task.status in {"running", "success"}:
                raise ValueError("正在发布或已成功的任务不能跳过")
            task.status = "skipped"
            db.add(PublishLog(task_id=task.id, level="info", message="用户跳过了该任务。"))
            add_audit_event(
                db,
                action="queue.skip",
                entity_type="publish_task",
                entity_id=task.id,
                outcome="success",
                message="用户跳过了该任务。",
            )
        job = self.scheduler.get_job(f"task-{task_id}")
        if job:
            self.scheduler.remove_job(job.id)
        with SessionLocal() as db:
            return db.get(PublishTask, task_id)

    def register_plan(self, plan_id: int) -> None:
        if not self.settings.publishing_enabled:
            if self.scheduler.get_job(f"plan-{plan_id}"):
                self.scheduler.remove_job(f"plan-{plan_id}")
            return
        if not self.scheduler.running:
            return
        with SessionLocal.begin() as db:
            plan = db.get(SchedulePlan, plan_id)
            if not plan or not plan.enabled:
                if self.scheduler.get_job(f"plan-{plan_id}"):
                    self.scheduler.remove_job(f"plan-{plan_id}")
                return
            expired = False
            if plan.scheduled_at:
                run_at = plan.scheduled_at
                if run_at < datetime.now(self.timezone).replace(tzinfo=None):
                    plan.enabled = False
                    plan.next_run_at = None
                    expired = True
                trigger = "date"
                next_run = run_at
            elif plan.cron_expr:
                cron = CronTrigger.from_crontab(plan.cron_expr, timezone=self.timezone)
                trigger = cron
                next_run = cron.get_next_fire_time(None, datetime.now(self.timezone)).replace(
                    tzinfo=None
                )
            else:
                return
        if expired:
            if self.scheduler.get_job(f"plan-{plan_id}"):
                self.scheduler.remove_job(f"plan-{plan_id}")
            return
        self.scheduler.add_job(
            self._run_plan,
            trigger,
            run_date=run_at if trigger == "date" else None,
            id=f"plan-{plan_id}",
            args=[plan_id],
            replace_existing=True,
        )
        with SessionLocal.begin() as db:
            plan = db.get(SchedulePlan, plan_id)
            plan.next_run_at = next_run

    def _run_plan(self, plan_id: int) -> None:
        from app.api.schedules import create_plan_tasks

        slot = datetime.now(self.timezone).strftime("%Y%m%d%H%M")
        create_plan_tasks(plan_id, slot)
        with SessionLocal.begin() as db:
            plan = db.get(SchedulePlan, plan_id)
            one_time = bool(plan and plan.scheduled_at)
            if one_time:
                plan.enabled = False
                plan.next_run_at = None
        if one_time and self.scheduler.get_job(f"plan-{plan_id}"):
            self.scheduler.remove_job(f"plan-{plan_id}")

    def remove_plan(self, plan_id: int) -> None:
        job = self.scheduler.get_job(f"plan-{plan_id}")
        if job:
            self.scheduler.remove_job(job.id)

    def reconcile(self) -> None:
        if not self.settings.publishing_enabled:
            return
        with SessionLocal() as db:
            task_ids = [
                task.id
                for task in db.scalars(
                    select(PublishTask).where(PublishTask.status == "pending")
                ).all()
            ]
            plan_ids = [
                plan.id
                for plan in db.scalars(
                    select(SchedulePlan).where(SchedulePlan.enabled.is_(True))
                ).all()
            ]
        for task_id in task_ids:
            if not self.scheduler.get_job(f"task-{task_id}"):
                self.enqueue(task_id)
        for plan_id in plan_ids:
            if not self.scheduler.get_job(f"plan-{plan_id}"):
                self.register_plan(plan_id)


queue_manager = QueueManager()
