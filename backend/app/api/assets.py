import base64
import io
import secrets
import uuid
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.schemas import AssetUpdate, ImageGenerationRequest
from app.config import get_settings
from app.core.media.assets import (
    normalize_tags,
    register_asset,
    resolve_asset_path,
    serialize_asset,
)
from app.storage.database import get_db
from app.storage.models import Draft, MediaAsset

router = APIRouter(tags=["assets"])
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.get("/assets")
def list_assets(
    kind: Literal["image", "video"] | None = None,
    tag: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(MediaAsset).order_by(MediaAsset.created_at.desc())
    if kind:
        query = query.where(MediaAsset.kind == kind)
    if tag:
        query = query.where(MediaAsset.tags.contains(tag.strip(), autoescape=True))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(MediaAsset.original_name.contains(pattern), MediaAsset.tags.contains(pattern))
        )
    return [serialize_asset(asset) for asset in db.scalars(query.limit(500)).all()]


@router.get("/assets/capabilities")
def asset_capabilities() -> dict:
    settings = get_settings()
    return {
        "image_generation_configured": bool(
            settings.image_base_url and settings.image_api_key and settings.image_model
        ),
        "max_image_upload_mb": MAX_IMAGE_BYTES // (1024 * 1024),
        "image_extensions": sorted(IMAGE_EXTENSIONS),
    }


@router.get("/assets/random")
def random_asset(
    kind: Literal["image", "video"] = "image",
    tag: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(MediaAsset).where(MediaAsset.kind == kind)
    if tag:
        query = query.where(MediaAsset.tags.contains(tag.strip(), autoescape=True))
    assets = db.scalars(query).all()
    if not assets:
        raise HTTPException(404, "没有匹配的素材，请先上传或调整标签。")
    return serialize_asset(secrets.choice(assets))


@router.post("/assets", status_code=201)
async def upload_asset(
    file: UploadFile = File(...),
    tags: str = Form(default=""),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(400, "图片仅支持 JPG、PNG 或 WebP。")
    if file.content_type and file.content_type not in IMAGE_MIME_TYPES:
        raise HTTPException(400, "上传文件的 MIME 类型不是受支持的图片格式。")
    settings = get_settings()
    output = settings.asset_dir / f"image-{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with output.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise HTTPException(400, "图片不能超过 10 MB。")
                target.write(chunk)
        if size == 0:
            raise HTTPException(400, "图片文件不能为空。")
        with Image.open(output) as image:
            image.verify()
        with Image.open(output) as image:
            if image.width * image.height > 40_000_000:
                raise HTTPException(400, "图片像素过高，请压缩后再上传。")
            mime_type = f"image/{image.format.lower()}"
            width, height = image.size
        asset = register_asset(
            db,
            f"assets/{output.name}",
            kind="image",
            original_name=file.filename or output.name,
            mime_type=mime_type,
            source="upload",
            tags=tags,
            size_bytes=size,
            width=width,
            height=height,
        )
        db.commit()
        db.refresh(asset)
        return serialize_asset(asset)
    except HTTPException:
        output.unlink(missing_ok=True)
        raise
    except (UnidentifiedImageError, OSError) as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(400, "图片文件无法识别。") from exc
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(500, "图片入库失败。") from exc


@router.post("/assets/generate", status_code=201)
async def generate_asset(request: ImageGenerationRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    if not (settings.image_base_url and settings.image_api_key and settings.image_model):
        raise HTTPException(
            503,
            "尚未配置 AI 生图服务，请在 .env 中设置 IMAGE_BASE_URL、IMAGE_API_KEY 和 IMAGE_MODEL。",
        )
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{settings.image_base_url.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {settings.image_api_key}"},
                json={
                    "model": settings.image_model,
                    "prompt": request.prompt,
                    "size": "1024x1024",
                    "response_format": "b64_json",
                },
            )
        response.raise_for_status()
        encoded = response.json()["data"][0]["b64_json"]
        content = base64.b64decode(encoded, validate=True)
        if not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError("生图结果为空或超过 10 MB。")
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("生图结果像素过高。")
            width, height = image.size
            converted = image.convert("RGB")
        output = settings.asset_dir / f"ai-{uuid.uuid4().hex}.png"
        converted.save(output, "PNG", optimize=True)
        asset = register_asset(
            db,
            f"assets/{output.name}",
            kind="image",
            original_name=f"{request.prompt[:40]}.png",
            mime_type="image/png",
            source="ai",
            tags=[*request.tags, "AI生成"],
            size_bytes=output.stat().st_size,
            width=width,
            height=height,
        )
        db.commit()
        db.refresh(asset)
        return serialize_asset(asset)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, KeyError, IndexError) as exc:
        raise HTTPException(502, "AI 生图服务返回了无法识别的图片。") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "AI 生图服务调用失败，请检查本机配置。") from exc


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: int, request: AssetUpdate, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    asset.tags = ",".join(normalize_tags(request.tags))
    db.commit()
    db.refresh(asset)
    return serialize_asset(asset)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise HTTPException(404, "素材不存在")
    referenced = db.scalar(
        select(Draft.id)
        .where(
            or_(
                Draft.cover_image == asset.url,
                Draft.video_path == asset.stored_path,
                Draft.body.contains(asset.url, autoescape=True),
            )
        )
        .limit(1)
    )
    if referenced:
        raise HTTPException(409, "该素材正被草稿使用，请先替换或删除对应草稿。")
    try:
        path = resolve_asset_path(asset.stored_path)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.delete(asset)
    db.flush()
    path.unlink(missing_ok=True)
    db.commit()
