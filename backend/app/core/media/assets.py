import hashlib
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.storage.models import MediaAsset


def normalize_tags(tags: list[str] | str) -> list[str]:
    values = tags.split(",") if isinstance(tags, str) else tags
    normalized = []
    for value in values:
        tag = value.strip().lstrip("#")
        if tag and tag not in normalized:
            normalized.append(tag[:30])
    return normalized[:10]


def stored_path_to_url(stored_path: str) -> str:
    folder, filename = stored_path.split("/", 1)
    prefix = {"assets": "/assets/", "covers": "/media/", "videos": "/videos/"}[folder]
    return prefix + filename


def resolve_asset_path(stored_path: str) -> Path:
    settings = get_settings()
    relative = Path(stored_path)
    roots = {
        "assets": settings.asset_dir,
        "covers": settings.data_dir / "covers",
        "videos": settings.video_dir,
    }
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] not in roots
        or ".." in relative.parts
    ):
        raise ValueError("素材路径无效。")
    path = settings.data_dir / relative
    if path.parent != roots[relative.parts[0]] or not path.is_file():
        raise ValueError("素材文件不存在。")
    return path


def serialize_asset(asset: MediaAsset) -> dict:
    return {
        "id": asset.id,
        "kind": asset.kind,
        "original_name": asset.original_name,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
        "width": asset.width,
        "height": asset.height,
        "duration": asset.duration,
        "stored_path": asset.stored_path,
        "url": asset.url,
        "sha256": asset.sha256,
        "source": asset.source,
        "tags": [tag for tag in asset.tags.split(",") if tag],
        "created_at": asset.created_at.isoformat(),
    }


def register_asset(
    db,
    stored_path: str,
    *,
    kind: str,
    original_name: str,
    mime_type: str = "",
    source: str,
    tags: list[str] | str | None = None,
    size_bytes: int | None = None,
    width: int | None = None,
    height: int | None = None,
    duration: int | None = None,
) -> MediaAsset:
    path = resolve_asset_path(stored_path)
    with path.open("rb") as source_file:
        digest = hashlib.file_digest(source_file, "sha256").hexdigest()
    asset = db.query(MediaAsset).filter(MediaAsset.stored_path == stored_path).one_or_none()
    if asset is None:
        asset = MediaAsset(
            stored_path=stored_path, url=stored_path_to_url(stored_path), sha256=digest
        )
        db.add(asset)
    asset.kind = kind
    asset.original_name = original_name[:300]
    asset.mime_type = mime_type[:120]
    asset.size_bytes = size_bytes if size_bytes is not None else path.stat().st_size
    asset.source = source
    asset.tags = ",".join(normalize_tags(tags or []))
    asset.width = width
    asset.height = height
    asset.duration = duration
    if kind == "image" and (width is None or height is None):
        with Image.open(path) as image:
            asset.width, asset.height = image.size
    db.flush()
    return asset
