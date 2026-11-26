import io
import json
import uuid

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete

from app.config import get_settings
from app.main import app
from app.storage.database import SessionLocal
from app.storage.models import Draft, MediaAsset, Preset


def image_bytes(color="#315d70") -> tuple[bytes, str]:
    output = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(output, "PNG")
    return output.getvalue(), "test-image.png"


def test_asset_upload_filter_update_and_delete():
    content, filename = image_bytes()
    asset_id = None
    try:
        with TestClient(app) as client:
            uploaded = client.post(
                "/api/assets",
                files={"file": (filename, content, "image/png")},
                data={"tags": "阶段4,封面"},
            )
            assert uploaded.status_code == 201, uploaded.text
            asset = uploaded.json()
            asset_id = asset["id"]
            assert asset["kind"] == "image"
            assert asset["width"] == 64 and asset["height"] == 48
            assert asset["url"].startswith("/assets/")
            filtered = client.get("/api/assets", params={"kind": "image", "tag": "阶段4"}).json()
            assert any(item["id"] == asset_id for item in filtered)
            random = client.get("/api/assets/random", params={"kind": "image", "tag": "阶段4"})
            assert random.status_code == 200
            updated = client.patch(f"/api/assets/{asset_id}", json={"tags": ["新标签"]})
            assert updated.status_code == 200
            assert updated.json()["tags"] == ["新标签"]
            assert client.delete(f"/api/assets/{asset_id}").status_code == 204
            asset_id = None
            assert not (get_settings().asset_dir / asset["stored_path"].split("/")[-1]).exists()
    finally:
        if asset_id:
            with SessionLocal.begin() as db:
                db.execute(delete(MediaAsset).where(MediaAsset.id == asset_id))


def test_generated_cover_automatically_enters_asset_library():
    title = f"阶段4封面入池-{uuid.uuid4().hex}"
    asset_id = None
    try:
        with TestClient(app) as client:
            response = client.post("/api/cover", data={"title": title})
            assert response.status_code == 200, response.text
            matches = client.get("/api/assets", params={"q": title}).json()
            assert len(matches) == 1
            asset_id = matches[0]["id"]
            assert matches[0]["source"] == "cover"
            assert matches[0]["url"] == response.json()["cover_url"]
    finally:
        if asset_id:
            with TestClient(app) as client:
                client.delete(f"/api/assets/{asset_id}")


def test_custom_preset_crud_preview_and_validation():
    preset_id = None
    style = {
        "fontFamily": "'Noto Serif SC','Songti SC',serif",
        "fontSize": 18,
        "lineHeight": 1.8,
        "paragraphSpacing": 20,
        "accent": "#123456",
        "headingStyle": "numbered",
        "quoteStyle": "line",
        "firstImageRule": "cover",
        "tailText": "阶段4自定义尾块",
    }
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/presets",
                json={
                    "name": "阶段4自定义模板",
                    "description": "测试模板",
                    "platform_hint": "general",
                    "style": style,
                },
            )
            assert created.status_code == 201, created.text
            preset_id = created.json()["id"]
            assert created.json()["is_builtin"] is False
            preview = client.post(
                "/api/preview",
                json={
                    "title": "自定义模板预览",
                    "body": "## 小节\n\n正文内容",
                    "preset_id": preset_id,
                    "compliance_enabled": False,
                },
            )
            assert preview.status_code == 200, preview.text
            assert "#123456" in preview.json()["html"]
            assert "阶段4自定义尾块" in preview.json()["html"]
            assert "preset-numbered" in preview.json()["html"]
            invalid = client.post(
                "/api/preview",
                json={
                    "title": "非法样式",
                    "body": "正文",
                    "preset_id": "fresh",
                    "style": {**style, "accent": "red;background:url(x)"},
                },
            )
            assert invalid.status_code == 422
            builtin_update = client.put(
                "/api/presets/fresh",
                json={
                    "name": "非法修改",
                    "description": "",
                    "platform_hint": "general",
                    "style": style,
                },
            )
            assert builtin_update.status_code == 409
            updated = client.put(
                f"/api/presets/{preset_id}",
                json={
                    "name": "阶段4自定义模板已修改",
                    "description": "测试模板",
                    "platform_hint": "zhihu",
                    "style": {**style, "accent": "#654321"},
                },
            )
            assert updated.status_code == 200
            assert updated.json()["style"]["accent"] == "#654321"
    finally:
        if preset_id:
            with SessionLocal.begin() as db:
                db.execute(delete(Preset).where(Preset.id == preset_id))


def test_draft_reuse_creates_independent_article_version():
    source_id = None
    reused_id = None
    title = f"阶段4复用原稿-{uuid.uuid4().hex}"
    try:
        with TestClient(app) as client:
            source = client.post(
                "/api/drafts",
                json={
                    "title": title,
                    "body": "原始正文",
                    "tags": ["复用"],
                    "content_type": "article",
                },
            )
            assert source.status_code == 201
            source_id = source.json()["id"]
            reused = client.post(
                f"/api/drafts/{source_id}/reuse",
                json={
                    "target_platform": "zhihu",
                    "adapt": False,
                },
            )
            assert reused.status_code == 201, reused.text
            reused_id = reused.json()["id"]
            assert reused_id != source_id
            assert reused.json()["source"] == "reuse"
            assert reused.json()["body"] == "原始正文"
            missing_model = client.post(
                f"/api/drafts/{source_id}/reuse",
                json={
                    "target_platform": "csdn",
                    "adapt": True,
                },
            )
            assert missing_model.status_code == 400
    finally:
        with SessionLocal.begin() as db:
            db.execute(
                delete(Draft).where(Draft.id.in_([item for item in (source_id, reused_id) if item]))
            )


def test_asset_capabilities_do_not_expose_secrets():
    with TestClient(app) as client:
        response = client.get("/api/assets/capabilities")
        assert response.status_code == 200
        assert set(response.json()) == {
            "image_generation_configured",
            "max_image_upload_mb",
            "image_extensions",
        }
        assert "key" not in json.dumps(response.json()).lower()
