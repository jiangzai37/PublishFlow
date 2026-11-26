from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=300)
    style: str = Field(default="清晰、自然、有信息量", max_length=300)
    length: int = Field(default=1200, ge=200, le=5000)
    with_headings: bool = True
    with_tags: bool = True


class PresetStyle(BaseModel):
    model_config = {"extra": "forbid"}

    fontFamily: str = Field(default="'Noto Serif SC','Songti SC',serif", max_length=120)
    fontSize: int = Field(default=16, ge=12, le=24)
    lineHeight: float = Field(default=1.9, ge=1.2, le=2.4)
    paragraphSpacing: int = Field(default=18, ge=6, le=36)
    accent: str = Field(default="#a44732", pattern=r"^#[0-9a-fA-F]{6}$")
    headingStyle: Literal["left-border", "numbered", "none"] = "left-border"
    quoteStyle: Literal["paper", "line", "none"] = "paper"
    firstImageRule: Literal["cover", "optional", "none"] = "cover"
    tailText: str = Field(default="", max_length=200)

    @field_validator("fontFamily")
    @classmethod
    def safe_font_family(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[\w\s,'\"-]+", value):
            raise ValueError("字体名称包含不安全字符")
        return value


class PreviewRequest(BaseModel):
    title: str = Field(default="", max_length=300)
    body: str = ""
    preset_id: str = "fresh"
    cover_url: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    style: PresetStyle | None = None


class VideoFields(BaseModel):
    video_path: str | None = Field(default=None, max_length=500)
    video_duration: int | None = Field(default=None, ge=0, le=86_400)
    video_width: int | None = Field(default=None, ge=0, le=32_768)
    video_height: int | None = Field(default=None, ge=0, le=32_768)
    video_partition: str | None = Field(default=None, max_length=120)
    video_collection: str | None = Field(default=None, max_length=120)


class DraftCreate(VideoFields):
    title: str = Field(default="未命名草稿", max_length=300)
    body: str = ""
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)
    cover_image: str | None = None
    content_type: Literal["article", "video"] = "article"


class DraftUpdate(VideoFields):
    title: str = Field(default="未命名草稿", max_length=300)
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    cover_image: str | None = None


class VideoProcessRequest(BaseModel):
    video_path: str = Field(min_length=1, max_length=500)
    title: str = Field(default="视频封面", min_length=1, max_length=300)
    at_seconds: float | None = Field(default=None, ge=0)


class AssetUpdate(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=10)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=10)


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=300)
    platform_hint: Literal["wechat", "zhihu", "general"] = "general"
    style: PresetStyle


class PresetUpdate(PresetCreate):
    pass


class DraftReuseRequest(BaseModel):
    target_platform: Literal["csdn", "zhihu"]
    adapt: bool = False


class MetricSnapshotRequest(BaseModel):
    task_id: int
    metric_date: date
    source: Literal["manual", "platform_export", "official_api"] = "manual"
    views: int = Field(default=0, ge=0, le=1_000_000_000_000)
    reads: int = Field(default=0, ge=0, le=1_000_000_000_000)
    plays: int = Field(default=0, ge=0, le=1_000_000_000_000)
    likes: int = Field(default=0, ge=0, le=1_000_000_000_000)
    comments: int = Field(default=0, ge=0, le=1_000_000_000_000)
    shares: int = Field(default=0, ge=0, le=1_000_000_000_000)
    favorites: int = Field(default=0, ge=0, le=1_000_000_000_000)
    note: str = Field(default="", max_length=300)
