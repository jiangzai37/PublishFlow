from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PublishPayload:
    title: str
    body: str
    rendered_html: str
    tags: list[str] = field(default_factory=list)
    cover_path: Path | None = None
    scheduled_at: object | None = None
    video_path: Path | None = None
    video_duration: int | None = None
    video_width: int | None = None
    video_height: int | None = None


@dataclass
class PublishResult:
    success: bool
    url: str | None = None
    message: str = ""
    requires_manual: bool = False
    retryable: bool = False
    uncertain: bool = False


class Adapter(ABC):
    platform: str
    display_name: str
    content_types: frozenset[str] = frozenset({"article"})
    title_limit: int | None = None

    @abstractmethod
    def login(self, cookie_json: str) -> dict[str, Any]:
        """Import a user-provided login session without bypassing platform checks."""

    @abstractmethod
    def publish(self, payload, cookies: list[dict], options: dict | None = None):
        """Publish to the user's own account and return a normalized result."""

    @abstractmethod
    def schedule(self, at):
        """Prepare a future publish plan."""

    @abstractmethod
    def check_status(self, task_id: str) -> dict[str, Any]:
        """Return the latest platform status for a published task."""

    @abstractmethod
    def get_author_profile(self, cookies: list[dict]) -> dict[str, Any]:
        """Read the signed-in account profile."""
