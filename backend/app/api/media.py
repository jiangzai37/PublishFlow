import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.schemas import VideoProcessRequest
from app.config import get_settings
from app.core.media.assets import register_asset
from app.core.media.cover import create_cover
from app.core.media.video import (
    VideoError,
    create_video_cover,
    ffmpeg_executable,
    transcode_video,
    validate_video,
)
from app.storage.database import get_db

router = APIRouter(tags=["media"])
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "application/octet-stream",
}


@router.post("/cover")
async def generate_cover(
    title: str = Form(...),
    background: UploadFile | None = None,
    db: Session = Depends(get_db),
):
    if not title.strip():
        raise HTTPException(400, "封面标题不能为空。")
    background_path = None
    if background:
        if background.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(400, "背景图仅支持 JPG、PNG 或 WebP。")
        settings = get_settings()
        background_path = settings.upload_dir / f"background-{uuid.uuid4().hex}.png"
        try:
            size = 0
            with background_path.open("wb") as target:
                while chunk := await background.read(1024 * 1024):
                    size += len(chunk)
                    if size > 10 * 1024 * 1024:
                        raise HTTPException(400, "背景图不能超过 10 MB。")
                    target.write(chunk)
            if size == 0:
                raise HTTPException(400, "背景图不能为空。")
            with Image.open(background_path) as image:
                image.verify()
            with Image.open(background_path) as image:
                if image.width * image.height > 40_000_000:
                    raise HTTPException(400, "背景图像素过高，请压缩后再上传。")
        except HTTPException:
            background_path.unlink(missing_ok=True)
            raise
        except (UnidentifiedImageError, OSError) as exc:
            background_path.unlink(missing_ok=True)
            raise HTTPException(400, "背景图文件无法识别。") from exc
        finally:
            if background_path and not background_path.exists():
                background_path = None
    try:
        cover_url = create_cover(title.strip(), background=background_path)
        register_asset(
            db,
            f"covers/{Path(cover_url).name}",
            kind="image",
            original_name=f"{title.strip()}.png",
            mime_type="image/png",
            source="cover",
            tags=["封面"],
        )
        db.commit()
        return {"cover_url": cover_url}
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "封面生成失败，请检查图片、字体与服务日志。") from exc


@router.get("/video/config")
def video_config() -> dict:
    settings = get_settings()
    try:
        ffmpeg_executable()
        available = True
    except VideoError:
        available = False
    return {
        "ffmpeg_available": available,
        "max_upload_mb": settings.max_video_upload_mb,
        "max_duration_seconds": settings.max_video_duration_seconds,
        "extensions": sorted(VIDEO_EXTENSIONS),
    }


@router.post("/videos")
async def upload_video(video: UploadFile, db: Session = Depends(get_db)):
    suffix = Path(video.filename or "").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "视频仅支持 MP4、MOV、WebM、MKV 或 M4V。")
    if video.content_type and video.content_type not in VIDEO_MIME_TYPES:
        raise HTTPException(400, "上传文件的 MIME 类型不是受支持的视频格式。")
    settings = get_settings()
    filename = f"video-{uuid.uuid4().hex}{suffix}"
    output = settings.video_dir / filename
    stored_path = f"videos/{filename}"
    size = 0
    try:
        with output.open("wb") as target:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_video_upload_mb * 1024 * 1024:
                    raise HTTPException(400, f"视频不能超过 {settings.max_video_upload_mb} MB。")
                target.write(chunk)
        if size == 0:
            raise HTTPException(400, "视频文件不能为空。")
        metadata = await run_in_threadpool(validate_video, stored_path)
        register_asset(
            db,
            stored_path,
            kind="video",
            original_name=video.filename or filename,
            mime_type=video.content_type or "video/mp4",
            source="upload",
            tags=["视频"],
            size_bytes=metadata.size_bytes,
            width=metadata.width,
            height=metadata.height,
            duration=metadata.duration,
        )
        db.commit()
        return metadata.to_dict()
    except HTTPException:
        output.unlink(missing_ok=True)
        raise
    except VideoError as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(500, "视频上传或校验失败。") from exc


@router.post("/video/transcode")
def process_video(request: VideoProcessRequest, db: Session = Depends(get_db)):
    try:
        metadata = transcode_video(request.video_path)
        register_asset(
            db,
            metadata.video_path,
            kind="video",
            original_name=f"{Path(request.video_path).stem}-transcoded.mp4",
            mime_type="video/mp4",
            source="transcode",
            tags=["视频", "转码"],
            size_bytes=metadata.size_bytes,
            width=metadata.width,
            height=metadata.height,
            duration=metadata.duration,
        )
        db.commit()
        return metadata.to_dict()
    except VideoError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "视频转码或入库失败。") from exc


@router.post("/video/cover")
def video_cover(request: VideoProcessRequest, db: Session = Depends(get_db)):
    try:
        cover_url = create_video_cover(request.video_path, request.title, request.at_seconds)
        register_asset(
            db,
            f"covers/{Path(cover_url).name}",
            kind="image",
            original_name=f"{request.title}-视频封面.png",
            mime_type="image/png",
            source="video_frame",
            tags=["视频封面"],
        )
        db.commit()
        return {"cover_url": cover_url}
    except VideoError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "视频封面生成或入库失败。") from exc
