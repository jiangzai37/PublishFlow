import importlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.main import app
from app.storage.database import SessionLocal, engine
from app.storage.models import (
    Account,
    AuditEvent,
    ComplianceDecision,
    Draft,
    PublishLog,
    PublishTask,
)


def test_health():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_untrusted_host_is_rejected():
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"Host": "evil.example"})
        assert response.status_code == 400


def test_cross_site_write_is_rejected():
    with TestClient(app) as client:
        response = client.post(
            "/api/drafts",
            json={"title": "跨站请求", "body": "不应写入"},
            headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
        )
        assert response.status_code == 403


def test_same_origin_write_is_allowed():
    with TestClient(app) as client:
        response = client.post(
            "/api/drafts",
            json={"title": "同源请求", "body": "正常写入"},
            headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
        )
        assert response.status_code == 201, response.text
        client.delete(f"/api/drafts/{response.json()['id']}")


def test_sqlite_foreign_keys_are_enabled():
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1


def test_presets_and_draft_round_trip():
    with TestClient(app) as client:
        presets = client.get("/api/presets")
        assert presets.status_code == 200
        assert len(presets.json()) >= 2
        created = client.post(
            "/api/drafts", json={"title": "测试草稿", "body": "正文", "tags": ["测试"]}
        )
        assert created.status_code == 201
        draft_id = created.json()["id"]
        updated = client.put(
            f"/api/drafts/{draft_id}", json={"title": "更新标题", "body": "更新正文", "tags": []}
        )
        assert updated.json()["title"] == "更新标题"
        client.delete(f"/api/drafts/{draft_id}")


def test_cover_multipart_upload():
    from io import BytesIO

    from PIL import Image

    with TestClient(app) as client:
        buffer = BytesIO()
        Image.new("RGB", (800, 400), "#ddd3c2").save(buffer, format="PNG")
        response = client.post(
            "/api/cover",
            data={"title": "接口封面测试"},
            files={"background": ("background.png", buffer.getvalue(), "image/png")},
        )
        assert response.status_code == 200
        assert response.json()["cover_url"].startswith("/media/")


def test_publish_requires_explicit_authorization():
    with TestClient(app) as client:
        draft = client.post("/api/drafts", json={"title": "授权测试", "body": "正文"}).json()
        account = client.post(
            "/api/accounts/cookies",
            json={
                "nickname": "测试账号",
                "cookie_json": '[{"name":"session","value":"test","domain":".csdn.net"}]',
            },
        ).json()
        response = client.post(
            "/api/publish",
            json={
                "draft_id": draft["id"],
                "account_id": account["id"],
                "preset_id": "fresh",
                "authorized": False,
            },
        )
        assert response.status_code == 400
        client.delete(f"/api/drafts/{draft['id']}")
        client.delete(f"/api/accounts/{account['id']}")


def test_publish_worker_commits_status_and_audit_in_one_transaction(monkeypatch):
    import importlib

    from app.auth.credentials import CredentialVault
    from app.storage.database import SessionLocal
    from app.storage.models import Account, Draft, PublishLog, PublishTask
    from publishers.base import PublishResult

    class FakeAdapter:
        display_name = "测试平台"

        def publish(self, payload, cookies):
            return PublishResult(True, url="https://article.csdn.net/test", message="ok")

    publish_module = importlib.import_module("app.api.publish")
    monkeypatch.setattr(publish_module, "get_adapter", lambda platform: FakeAdapter())

    with SessionLocal() as db:
        account = Account(
            platform="csdn",
            nickname="事务测试",
            cookie_encrypted=CredentialVault().encrypt(
                '[{"name":"session","value":"test","domain":".csdn.net"}]'
            ),
        )
        db.add(account)
        db.flush()
        draft = Draft(title="事务测试", body="正文", source="manual")
        db.add(draft)
        db.flush()
        task = PublishTask(
            draft_id=draft.id, account_id=account.id, platform="csdn", preset_id="fresh"
        )
        db.add(task)
        db.commit()
        task_id, draft_id, account_id = task.id, draft.id, account.id

    publish_module.run_publish(task_id)

    with SessionLocal() as db:
        task = db.get(PublishTask, task_id)
        assert task.status == "success"
        assert task.result_url == "https://article.csdn.net/test"
        logs = db.query(PublishLog).filter(PublishLog.task_id == task_id).all()
        assert any("成功回执" in log.message for log in logs)
        db.delete(task)
        db.delete(db.get(Draft, draft_id))
        db.delete(db.get(Account, account_id))
        db.commit()


def test_publish_idempotency_and_snapshot_freeze_authorized_content(monkeypatch):
    from publishers.base import PublishResult

    captured = {}

    class FakeAdapter:
        display_name = "测试平台"
        content_types = frozenset({"article"})

        def publish(self, payload, cookies):
            captured["title"] = payload.title
            captured["body"] = payload.body
            return PublishResult(True, url="https://example.com/frozen", message="ok")

    publish_module = importlib.import_module("app.api.publish")
    monkeypatch.setattr(publish_module, "get_adapter", lambda platform: FakeAdapter())
    task_id = None
    with TestClient(app) as client:
        draft = client.post(
            "/api/drafts", json={"title": "授权时的标题", "body": "授权时的正文"}
        ).json()
        account = client.post(
            "/api/accounts/cookies",
            json={
                "nickname": "快照测试账号",
                "cookie_json": '[{"name":"session","value":"test","domain":".csdn.net"}]',
            },
        ).json()
        payload = {
            "draft_id": draft["id"],
            "account_id": account["id"],
            "preset_id": "fresh",
            "authorized": True,
            "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "max_retries": 0,
            "idempotency_key": "snapshot-freeze-test-key",
        }
        try:
            first = client.post("/api/publish", json=payload)
            assert first.status_code == 202, first.text
            task_id = first.json()["id"]
            second = client.post("/api/publish", json=payload)
            assert second.status_code == 202, second.text
            assert second.json()["id"] == task_id
            duplicate = client.post("/api/publish", json={**payload, "idempotency_key": None})
            assert duplicate.status_code == 409

            updated = client.put(
                f"/api/drafts/{draft['id']}",
                json={
                    "title": "包含破解内容的后续编辑",
                    "body": "这段内容不属于已授权任务。",
                    "tags": [],
                },
            )
            assert updated.status_code == 200, updated.text
            publish_module.run_publish(task_id)

            assert captured == {"title": "授权时的标题", "body": "授权时的正文"}
            with SessionLocal() as db:
                task = db.get(PublishTask, task_id)
                assert task.status == "success"
                assert task.snapshot_json
                assert "后续编辑" not in task.snapshot_json
        finally:
            with SessionLocal.begin() as db:
                task = db.get(PublishTask, task_id) if task_id else None
                if task:
                    db.execute(
                        delete(AuditEvent).where(
                            AuditEvent.entity_type == "publish_task",
                            AuditEvent.entity_id == task_id,
                        )
                    )
                    for decision in db.scalars(
                        select(ComplianceDecision).where(ComplianceDecision.task_id == task_id)
                    ).all():
                        db.delete(decision)
                    for log in db.scalars(
                        select(PublishLog).where(PublishLog.task_id == task_id)
                    ).all():
                        db.delete(log)
                    db.delete(task)
                db.delete(db.get(Draft, draft["id"]))
                db.delete(db.get(Account, account["id"]))


def test_uncertain_submission_cannot_be_retried(monkeypatch):
    from app.auth.credentials import CredentialVault
    from publishers.base import PublishResult

    class FakeAdapter:
        display_name = "测试平台"

        def publish(self, payload, cookies):
            return PublishResult(
                False,
                message="提交后未收到成功回执",
                requires_manual=True,
                retryable=True,
                uncertain=True,
            )

    publish_module = importlib.import_module("app.api.publish")
    monkeypatch.setattr(publish_module, "get_adapter", lambda platform: FakeAdapter())
    with SessionLocal.begin() as db:
        account = Account(
            platform="csdn",
            nickname="不确定结果测试",
            cookie_encrypted=CredentialVault().encrypt('[{"name":"session","value":"test"}]'),
        )
        draft = Draft(title="不确定结果测试", body="正文", source="manual")
        db.add_all([account, draft])
        db.flush()
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
            max_retries=3,
        )
        db.add(task)
        db.commit()
        task_id, draft_id, account_id = task.id, draft.id, account.id
    try:
        publish_module.run_publish(task_id)
        with SessionLocal() as db:
            stored = db.get(PublishTask, task_id)
            assert stored.status == "failed"
            assert stored.submission_uncertain is True
            assert stored.retry_count == 0
        with TestClient(app) as client:
            response = client.post(f"/api/tasks/{task_id}/retry")
            assert response.status_code == 409
            assert "平台确认" in response.json()["detail"]
    finally:
        with SessionLocal.begin() as db:
            db.execute(
                delete(AuditEvent).where(
                    AuditEvent.entity_type == "publish_task", AuditEvent.entity_id == task_id
                )
            )
            for decision in db.scalars(
                select(ComplianceDecision).where(ComplianceDecision.task_id == task_id)
            ).all():
                db.delete(decision)
            for log in db.scalars(select(PublishLog).where(PublishLog.task_id == task_id)).all():
                db.delete(log)
            task = db.get(PublishTask, task_id)
            if task:
                db.delete(task)
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


def test_publishing_can_be_disabled_at_api_and_worker_boundaries(monkeypatch):
    from app.auth.credentials import CredentialVault
    from app.storage.database import SessionLocal
    from app.storage.models import Account, Draft, PublishTask

    publish_module = importlib.import_module("app.api.publish")
    schedules_module = importlib.import_module("app.api.schedules")
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(publish_module.settings, "publishing_enabled", False)
    monkeypatch.setattr(schedules_module.settings, "publishing_enabled", False)
    monkeypatch.setattr(main_module.settings, "publishing_enabled", False)
    monkeypatch.setattr(
        publish_module,
        "get_adapter",
        lambda platform: (_ for _ in ()).throw(AssertionError("禁用模式不应调用适配器")),
    )
    with SessionLocal.begin() as db:
        account = Account(
            platform="csdn",
            nickname="禁用发布测试",
            cookie_encrypted=CredentialVault().encrypt('[{"name":"session","value":"test"}]'),
        )
        draft = Draft(title="禁用发布测试", body="正文", source="manual")
        db.add_all([account, draft])
        db.flush()
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
        )
        db.add(task)
        db.commit()
        account_id, draft_id, task_id = account.id, draft.id, task.id
    try:
        publish_module.run_publish(task_id)
        with SessionLocal() as db:
            stored = db.get(PublishTask, task_id)
            assert stored.status == "failed"
            assert stored.submission_uncertain is False
            assert "禁用真实发布" in stored.error_msg
        with TestClient(app) as client:
            assert client.get("/api/health").json()["publishing_enabled"] is False
            payload = {
                "draft_id": draft_id,
                "account_id": account_id,
                "preset_id": "fresh",
                "authorized": True,
            }
            assert client.post("/api/publish", json=payload).status_code == 503
            assert (
                client.post(
                    "/api/schedules",
                    json={
                        **payload,
                        "name": "禁用计划",
                        "account_ids": [account_id],
                        "cron_expr": "30 9 * * *",
                    },
                ).status_code
                == 503
            )
    finally:
        with SessionLocal.begin() as db:
            db.execute(
                delete(AuditEvent).where(
                    AuditEvent.entity_type == "publish_task", AuditEvent.entity_id == task_id
                )
            )
            for decision in db.scalars(
                select(ComplianceDecision).where(ComplianceDecision.task_id == task_id)
            ).all():
                db.delete(decision)
            for log in db.scalars(select(PublishLog).where(PublishLog.task_id == task_id)).all():
                db.delete(log)
            db.delete(db.get(PublishTask, task_id))
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


def test_relative_storage_paths_use_project_root():
    from app.config import PROJECT_DIR, Settings

    settings = Settings(data_dir=Path("./isolated-data"), upload_dir="./isolated-uploads")
    assert settings.data_dir == PROJECT_DIR / "isolated-data"
    assert settings.upload_dir == PROJECT_DIR / "isolated-uploads"


def test_task_response_strips_url_secrets(monkeypatch):
    from app.api.publish import serialize_task
    from app.auth.credentials import CredentialVault

    with SessionLocal.begin() as db:
        account = Account(
            platform="csdn",
            nickname="脱敏测试",
            cookie_encrypted=CredentialVault().encrypt('[{"name":"session","value":"test"}]'),
        )
        draft = Draft(title="脱敏测试", body="正文", source="manual")
        db.add_all([account, draft])
        db.flush()
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
            status="failed",
            result_url="https://example.com/article?token=secret-value#fragment",
            error_msg="失败 token=secret-value https://example.com/?key=private",
        )
        db.add(task)
        db.commit()
        task_id = task.id
        draft_id = draft.id
        account_id = account.id
    try:
        with SessionLocal() as db:
            result = serialize_task(db.get(PublishTask, task_id), db)
        assert result["result_url"] == "https://example.com/article"
        assert "secret-value" not in result["error_msg"]
        assert "?key=private" not in result["error_msg"]
    finally:
        with SessionLocal.begin() as db:
            db.delete(db.get(PublishTask, task_id))
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))
