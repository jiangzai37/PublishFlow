import json
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.publish import create_publish_snapshot
from app.api.schedules import create_plan_tasks
from app.auth.credentials import CredentialVault, parse_cookie_payload
from app.config import get_settings
from app.core.media.video import (
    VideoError,
    create_video_cover,
    resolve_video_path,
    transcode_video,
    validate_video,
)
from app.main import app
from app.storage.database import SessionLocal
from app.storage.models import Account, Draft, Preset, PublishLog, PublishTask, SchedulePlan
from publishers.base import PublishResult
from publishers.registry import get_adapter


def create_sample_video() -> tuple[Path, str]:
    settings = get_settings()
    name = f"test-video-{uuid.uuid4().hex}.mp4"
    path = settings.video_dir / name
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x315d70:s=640x360:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return path, f"videos/{name}"


def delete_task(db, task: PublishTask) -> None:
    for log in db.scalars(select(PublishLog).where(PublishLog.task_id == task.id)).all():
        db.delete(log)
    db.delete(task)


def test_video_path_cannot_escape_upload_directory():
    with pytest.raises(VideoError):
        resolve_video_path("../publishflow.db")
    with pytest.raises(VideoError):
        resolve_video_path("videos/../../publishflow.db")


def test_video_probe_transcode_and_cover_roundtrip():
    path, stored = create_sample_video()
    encoded_path = None
    cover_path = None
    try:
        metadata = validate_video(stored)
        assert metadata.duration == 2
        assert (metadata.width, metadata.height) == (640, 360)
        encoded = transcode_video(stored)
        encoded_path = get_settings().video_dir / encoded.video_path.split("/")[-1]
        assert encoded.duration == 2
        assert encoded.size_bytes > 0
        cover_url = create_video_cover(stored, "视频验收", at_seconds=0.5)
        cover_path = get_settings().data_dir / "covers" / cover_url.rsplit("/", 1)[-1]
        assert cover_path.is_file()
    finally:
        path.unlink(missing_ok=True)
        if encoded_path:
            encoded_path.unlink(missing_ok=True)
        if cover_path:
            cover_path.unlink(missing_ok=True)


def test_video_upload_and_video_publish_validation():
    path, stored = create_sample_video()
    with SessionLocal() as db:
        article_account = Account(
            platform="csdn",
            nickname="阶段3文章账号",
            cookie_encrypted=CredentialVault().encrypt('[{"name":"session","value":"test"}]'),
        )
        video_account = Account(
            platform="bilibili",
            nickname="阶段3视频账号",
            cookie_encrypted=CredentialVault().encrypt('[{"name":"SESSDATA","value":"test"}]'),
        )
        db.add_all([article_account, video_account])
        db.commit()
        article_id, video_id = article_account.id, video_account.id
    draft_id = None
    try:
        with TestClient(app) as client:
            with path.open("rb") as video:
                uploaded = client.post(
                    "/api/videos",
                    files={"video": (path.name, video, "video/mp4")},
                )
            assert uploaded.status_code == 200, uploaded.text
            metadata = uploaded.json()
            assert metadata["duration"] == 2
            assert metadata["video_path"].startswith("videos/")
            draft = client.post(
                "/api/drafts",
                json={
                    "title": "阶段3视频发布验收",
                    "body": "用于验证视频队列与平台能力边界。",
                    "content_type": "video",
                    "tags": ["测试"],
                    "video_path": metadata["video_path"],
                    "video_duration": metadata["duration"],
                    "video_width": metadata["width"],
                    "video_height": metadata["height"],
                    "video_partition": "知识",
                    "video_collection": "阶段3测试",
                },
            )
            assert draft.status_code == 201, draft.text
            draft_id = draft.json()["id"]
            assert draft.json()["content_type"] == "video"
            mismatch = client.post(
                "/api/publish",
                json={
                    "draft_id": draft_id,
                    "account_id": article_id,
                    "authorized": True,
                },
            )
            assert mismatch.status_code == 400
            assert "不支持" in mismatch.json()["detail"]
            scheduled = datetime.now(ZoneInfo(get_settings().schedule_timezone)) + timedelta(
                hours=1
            )
            published = client.post(
                "/api/publish",
                json={
                    "draft_id": draft_id,
                    "account_id": video_id,
                    "authorized": True,
                    "scheduled_at": scheduled.isoformat(),
                },
            )
            assert published.status_code == 202, published.text
            assert published.json()["content_type"] == "video"
            assert published.json()["status"] == "pending"
    finally:
        with SessionLocal.begin() as db:
            if draft_id:
                for task in db.scalars(
                    select(PublishTask).where(PublishTask.draft_id == draft_id)
                ).all():
                    delete_task(db, task)
                draft = db.get(Draft, draft_id)
                if draft:
                    db.delete(draft)
            db.delete(db.get(Account, article_id))
            db.delete(db.get(Account, video_id))
        path.unlink(missing_ok=True)
        metadata_path = get_settings().video_dir / stored.split("/")[-1]
        metadata_path.unlink(missing_ok=True)


def test_video_schedule_inherits_content_type(monkeypatch):
    path, stored = create_sample_video()
    with SessionLocal() as db:
        account = Account(
            platform="bilibili",
            nickname="阶段3调度账号",
            cookie_encrypted=CredentialVault().encrypt('[{"name":"SESSDATA","value":"test"}]'),
        )
        draft = Draft(
            title="视频周期计划",
            body="",
            content_type="video",
            video_path=stored,
            video_duration=2,
            video_width=640,
            video_height=360,
            video_partition="知识",
        )
        db.add_all([account, draft])
        db.flush()
        preset = db.get(Preset, "fresh")
        snapshot, _ = create_publish_snapshot(draft, preset, db)
        plan = SchedulePlan(
            name="阶段3视频计划",
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
        task_ids = create_plan_tasks(plan_id, "202611260900")
        assert len(task_ids) == 1
        with SessionLocal() as db:
            task = db.get(PublishTask, task_ids[0])
            assert task.content_type == "video"
            assert task.platform == "bilibili"
    finally:
        with SessionLocal.begin() as db:
            for task in db.scalars(
                select(PublishTask).where(PublishTask.schedule_plan_id == plan_id)
            ).all():
                delete_task(db, task)
            db.delete(db.get(SchedulePlan, plan_id))
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))
        path.unlink(missing_ok=True)


def test_bilibili_credentials_and_adapter_capability():
    raw = json.dumps(
        [
            {"name": "SESSDATA", "value": "secret", "domain": ".bilibili.com"},
            {"name": "other", "value": "ignored", "domain": ".example.com"},
        ]
    )
    cookies = parse_cookie_payload(raw, "bilibili")
    assert [cookie["name"] for cookie in cookies] == ["SESSDATA"]
    adapter = get_adapter("bilibili")
    assert adapter.content_types == frozenset({"video"})
    assert adapter.title_limit == 80


def test_video_worker_passes_metadata_and_partition(monkeypatch):
    path, stored = create_sample_video()
    captured = {}

    class FakeVideoAdapter:
        display_name = "B站"
        content_types = frozenset({"video"})

        def publish(self, payload, cookies, options=None):
            captured.update(
                {
                    "duration": payload.video_duration,
                    "width": payload.video_width,
                    "video_path": str(payload.video_path),
                    "partition": options["partition"],
                    "collection": options["collection"],
                }
            )
            return PublishResult(
                True, url="https://member.bilibili.com/platform/upload-manage/article"
            )

    import app.api.publish as publish_module

    monkeypatch.setattr(publish_module, "get_adapter", lambda platform: FakeVideoAdapter())
    with SessionLocal() as db:
        account = Account(
            platform="bilibili",
            nickname="阶段3 Worker 账号",
            cookie_encrypted=CredentialVault().encrypt('[{"name":"SESSDATA","value":"test"}]'),
        )
        draft = Draft(
            title="视频 Worker 验收",
            body="",
            content_type="video",
            video_path=stored,
            video_duration=2,
            video_width=640,
            video_height=360,
            video_partition="知识",
            video_collection="测试合集",
        )
        db.add_all([account, draft])
        db.flush()
        task = PublishTask(
            draft_id=draft.id,
            account_id=account.id,
            platform="bilibili",
            content_type="video",
            preset_id="fresh",
            status="pending",
        )
        db.add(task)
        db.commit()
        account_id, draft_id, task_id = account.id, draft.id, task.id
    try:
        publish_module.run_publish(task_id)
        assert captured["duration"] == 2
        assert captured["width"] == 640
        assert captured["partition"] == "知识"
        assert captured["collection"] == "测试合集"
        with SessionLocal() as db:
            task = db.get(PublishTask, task_id)
            assert task.status == "success"
            assert db.get(Draft, draft_id).status == "published"
    finally:
        with SessionLocal.begin() as db:
            task = db.get(PublishTask, task_id)
            if task:
                delete_task(db, task)
            db.delete(db.get(Draft, draft_id))
            db.delete(db.get(Account, account_id))
        path.unlink(missing_ok=True)
