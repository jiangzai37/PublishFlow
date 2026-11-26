import importlib
import json
import uuid
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.publish import prepare_draft_content
from app.auth.credentials import CredentialVault
from app.main import app
from app.storage.audit import sanitize_metadata, sanitize_text
from app.storage.database import SessionLocal
from app.storage.models import Account, AuditEvent, ComplianceDecision, Draft, Preset, PublishTask
from publishers.base import PublishResult


def test_mutation_audit_is_structured_and_redacted():
    request_ids = []
    draft_id = None
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/drafts",
                json={
                    "title": "阶段5审计测试",
                    "body": "secret-body-value",
                    "tags": ["审计"],
                },
            )
            assert created.status_code == 201, created.text
            draft_id = created.json()["id"]
            request_ids.append(created.headers["x-request-id"])
            denied = client.post(
                "/api/publish",
                json={
                    "draft_id": draft_id,
                    "account_id": 999999,
                    "authorized": False,
                },
            )
            assert denied.status_code == 404
            request_ids.append(denied.headers["x-request-id"])
            events = client.get("/api/audit", params={"limit": 200}).json()
            matched = [event for event in events if event["request_id"] in request_ids]
            assert len(matched) == 2
            assert {event["outcome"] for event in matched} == {"success", "denied"}
            serialized = json.dumps(matched, ensure_ascii=False)
            assert "secret-body-value" not in serialized
            assert all(event["actor"] == "local" for event in matched)
            assert all("path" in event["metadata"] for event in matched)
    finally:
        if draft_id:
            with TestClient(app) as client:
                deleted = client.delete(f"/api/drafts/{draft_id}")
                if deleted.status_code == 204:
                    request_ids.append(deleted.headers["x-request-id"])
        with SessionLocal.begin() as db:
            db.execute(delete(AuditEvent).where(AuditEvent.request_id.in_(request_ids)))


def test_audit_sanitizes_nested_secrets_and_url_queries():
    metadata = sanitize_metadata(
        {
            "access_token": "secret-token",
            "result_url": "https://example.com/article?token=secret#fragment",
            "nested": {"apiKey": "secret-key", "message": "查看 https://example.com/a?key=secret"},
        }
    )
    assert metadata["access_token"] == "[REDACTED]"
    assert metadata["result_url"] == "https://example.com/article"
    assert metadata["nested"]["apiKey"] == "[REDACTED]"
    assert "secret" not in metadata["nested"]["message"]
    assert sanitize_text("失败 token=secret-value") == "失败 token=[REDACTED]"


def test_worker_revalidates_changed_content_before_publish(monkeypatch):
    publish_module = importlib.import_module("app.api.publish")
    called = False

    class FakeAdapter:
        display_name = "测试平台"

        def publish(self, payload, cookies):
            nonlocal called
            called = True
            return PublishResult(True, url="https://example.com/article", message="ok")

    monkeypatch.setattr(publish_module, "get_adapter", lambda platform: FakeAdapter())
    with SessionLocal.begin() as db:
        account = Account(
            platform="csdn",
            nickname="阶段5合规测试",
            cookie_encrypted=CredentialVault().encrypt(
                '[{"name":"session","value":"test","domain":".csdn.net"}]'
            ),
        )
        draft = Draft(title="合规测试", body="初始正文", source="manual")
        db.add(account)
        db.add(draft)
        db.flush()
        task = PublishTask(
            draft_id=draft.id, account_id=account.id, platform="csdn", preset_id="fresh"
        )
        db.add(task)
        db.flush()
        db.add(
            ComplianceDecision(
                task_id=task.id,
                content_sha256="outdated",
                ruleset_version="2026-11-26",
                passed=True,
                findings_json="[]",
                ad_acknowledged=True,
            )
        )
        task_id, draft_id, account_id = task.id, draft.id, account.id

    with SessionLocal.begin() as db:
        db.get(Draft, draft_id).body = "这里包含破解内容"

    publish_module.run_publish(task_id)

    with SessionLocal() as db:
        task = db.get(PublishTask, task_id)
        assert called is False
        assert task.status == "failed"
        assert "合规" in task.error_msg
        decision = (
            db.query(ComplianceDecision)
            .filter(ComplianceDecision.task_id == task_id)
            .order_by(ComplianceDecision.id.desc())
            .first()
        )
        assert decision.passed is False
        assert any(item["type"] == "prohibited" for item in json.loads(decision.findings_json))
        audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.entity_id == task_id,
                AuditEvent.action == "publish.compliance",
            )
            .order_by(AuditEvent.id.desc())
            .first()
        )
        assert audit.outcome == "denied"
        db.execute(
            delete(AuditEvent).where(
                AuditEvent.entity_type == "publish_task", AuditEvent.entity_id == task_id
            )
        )
        db.delete(task)
        db.delete(db.get(Draft, draft_id))
        db.delete(db.get(Account, account_id))
        db.commit()


def test_preview_checks_rendered_footer_and_tags():
    with TestClient(app) as client:
        style = client.get("/api/presets/fresh").json()["style"]
        response = client.post(
            "/api/preview",
            json={
                "title": "正常标题",
                "body": "正常正文",
                "preset_id": "fresh",
                "compliance_enabled": True,
                "tags": ["最好"],
                "style": {**style, "tailText": "包含破解内容"},
            },
        )
        assert response.status_code == 200, response.text
        findings = response.json()["findings"]
        assert any(item["type"] == "prohibited" for item in findings)
        assert any(item["type"] == "advertising" for item in findings)


def test_template_change_invalidates_advertising_acknowledgement(monkeypatch):
    publish_module = importlib.import_module("app.api.publish")
    called = False

    class FakeAdapter:
        display_name = "测试平台"

        def publish(self, payload, cookies):
            nonlocal called
            called = True
            return PublishResult(True, url="https://example.com/article", message="ok")

    monkeypatch.setattr(publish_module, "get_adapter", lambda platform: FakeAdapter())
    preset_id = f"custom-compliance-{uuid.uuid4().hex}"
    with SessionLocal.begin() as db:
        account = Account(
            platform="csdn",
            nickname="阶段5模板合规测试",
            cookie_encrypted=CredentialVault().encrypt(
                '[{"name":"session","value":"test","domain":".csdn.net"}]'
            ),
        )
        draft = Draft(title="模板合规测试", body="初始正文", source="manual")
        style = json.loads(db.get(Preset, "fresh").style_json)
        preset = Preset(
            id=preset_id,
            name="模板合规测试",
            description="",
            platform_hint="general",
            style_json=json.dumps(style, ensure_ascii=False),
            is_builtin=False,
        )
        db.add(account)
        db.add(draft)
        db.add(preset)
        db.flush()
        task = PublishTask(
            draft_id=draft.id, account_id=account.id, platform="csdn", preset_id=preset.id
        )
        db.add(task)
        db.flush()
        _, fingerprint, _, _, _ = prepare_draft_content(draft, preset, db)
        db.add(
            ComplianceDecision(
                task_id=task.id,
                content_sha256=fingerprint,
                ruleset_version="2026-11-26",
                passed=True,
                findings_json="[]",
                ad_acknowledged=True,
            )
        )
        task_id, draft_id, account_id = task.id, draft.id, account.id

    with SessionLocal.begin() as db:
        preset = db.get(Preset, preset_id)
        style = json.loads(preset.style_json)
        style["tailText"] = "行业第一"
        preset.style_json = json.dumps(style, ensure_ascii=False)

    publish_module.run_publish(task_id)

    with SessionLocal() as db:
        task = db.get(PublishTask, task_id)
        assert called is False
        assert task.status == "failed"
        assert "合规" in task.error_msg
        decision = (
            db.query(ComplianceDecision)
            .filter(ComplianceDecision.task_id == task_id)
            .order_by(ComplianceDecision.id.desc())
            .first()
        )
        assert decision.passed is False
        assert any(item["type"] == "advertising" for item in json.loads(decision.findings_json))
        db.execute(
            delete(AuditEvent).where(
                AuditEvent.entity_type == "publish_task", AuditEvent.entity_id == task_id
            )
        )
        db.delete(task)
        db.delete(db.get(Preset, preset_id))
        db.delete(db.get(Draft, draft_id))
        db.delete(db.get(Account, account_id))
        db.commit()


def test_analytics_period_totals_and_success_rate_use_same_window():
    with TestClient(app) as client:
        before = client.get("/api/analytics", params={"days": 7}).json()
    with SessionLocal.begin() as db:
        account = Account(platform="csdn", nickname="阶段5周期统计测试", cookie_encrypted="test")
        draft = Draft(title="阶段5周期统计文章", body="正文", source="manual")
        db.add(account)
        db.add(draft)
        db.flush()
        old_task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
            status="success",
            created_at=datetime.now() - timedelta(days=30),
        )
        recent_task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
            status="failed",
            created_at=datetime.now(),
        )
        db.add(old_task)
        db.add(recent_task)
        db.commit()
        task_ids = [old_task.id, recent_task.id]
        draft_id, account_id = draft.id, account.id

    try:
        with TestClient(app) as client:
            after = client.get("/api/analytics", params={"days": 7}).json()
        assert after["summary"]["total_tasks"] == before["summary"]["total_tasks"] + 2
        assert after["summary"]["period_tasks"] == before["summary"]["period_tasks"] + 1
        assert after["summary"]["success"] == before["summary"]["success"]
        assert after["summary"]["failed"] == before["summary"]["failed"] + 1
        expected_rate = (
            round(after["summary"]["success"] / after["summary"]["period_tasks"] * 100, 1)
            if after["summary"]["period_tasks"]
            else 0
        )
        assert after["summary"]["success_rate"] == expected_rate
        platform = next(item for item in after["platforms"] if item["platform"] == "csdn")
        before_platform = next(
            (item for item in before["platforms"] if item["platform"] == "csdn"),
            {"total": 0},
        )
        assert platform["total"] == before_platform["total"] + 1
    finally:
        with SessionLocal.begin() as db:
            for task_id in task_ids:
                task = db.get(PublishTask, task_id)
                if task:
                    db.delete(task)
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))


def test_metric_import_is_idempotent_and_feeds_analytics():
    with SessionLocal.begin() as db:
        account = Account(platform="csdn", nickname="阶段5看板测试", cookie_encrypted="test")
        draft = Draft(title="阶段5看板文章", body="正文", source="manual")
        db.add(account)
        db.add(draft)
        db.flush()
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="csdn",
            preset_id="fresh",
            status="success",
            result_url="https://example.com/stage5",
        )
        db.add(task)
        db.commit()
        task_id, draft_id, account_id = task.id, draft.id, account.id

    request_ids = []
    try:
        with TestClient(app) as client:
            before = client.get("/api/analytics", params={"days": 30}).json()
            payload = {
                "task_id": task_id,
                "metric_date": date.today().isoformat(),
                "source": "manual",
                "views": 100,
                "reads": 80,
                "likes": 5,
                "comments": 2,
                "note": "阶段5测试数据",
            }
            first = client.post("/api/metrics", json=payload)
            assert first.status_code == 201, first.text
            request_ids.append(first.headers["x-request-id"])
            payload["views"] = 150
            second = client.post("/api/metrics", json=payload)
            assert second.status_code == 201, second.text
            request_ids.append(second.headers["x-request-id"])
            assert second.json()["id"] == first.json()["id"]
            after = client.get("/api/analytics", params={"days": 30}).json()
            assert after["metrics"]["views"] == before["metrics"]["views"] + 150
            assert after["metrics"]["engagement"] == before["metrics"]["engagement"] + 7
            assert any(item["platform"] == "csdn" for item in after["platforms"])
            snapshots = client.get("/api/metrics", params={"task_id": task_id}).json()
            assert len(snapshots) == 1
            assert snapshots[0]["source"] == "manual"
    finally:
        with SessionLocal.begin() as db:
            db.execute(delete(AuditEvent).where(AuditEvent.request_id.in_(request_ids)))
            task = db.get(PublishTask, task_id)
            if task:
                db.delete(task)
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))
