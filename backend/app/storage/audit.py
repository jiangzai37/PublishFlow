import json
import re
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from app.storage.models import AuditEvent, PublishLog

request_id_context: ContextVar[str] = ContextVar("audit_request_id", default="system")
SENSITIVE_KEYS = {
    "authorization",
    "body",
    "content",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "headers",
    "key",
    "password",
    "payload",
    "secret",
    "token",
}
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")
SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|token|api[_-]?key|password|secret)\s*[:=]\s*[^,\s;]+"
)


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in SENSITIVE_KEYS or normalized.endswith(
        ("token", "password", "secret", "credential", "authorization", "cookie", "apikey")
    )


def sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return value[:500]
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:500]
    except ValueError:
        return value[:500]


def sanitize_text(value: str, limit: int = 500) -> str:
    text = URL_PATTERN.sub(lambda match: sanitize_url(match.group(0).rstrip(".,;")), value)
    text = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text[:limit]


def log_task_event(task_id: int, level: str, message: str) -> None:
    from app.storage.database import SessionLocal

    with SessionLocal.begin() as db:
        db.add(PublishLog(task_id=task_id, level=level, message=sanitize_text(message, 2000)))


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)[:80]
            normalized_key = re.sub(r"[^a-z0-9]", "", key_text.lower())
            if _is_sensitive_key(key_text):
                sanitized[key_text] = "[REDACTED]"
            elif normalized_key.endswith("url") and isinstance(item, str):
                sanitized[key_text] = sanitize_url(item)
            else:
                sanitized[key_text] = sanitize_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value[:50]]
    if isinstance(value, str):
        return sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:500]


def add_audit_event(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None,
    outcome: str,
    message: str,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor="local",
        action=action[:120],
        entity_type=entity_type[:80],
        entity_id=entity_id,
        outcome=outcome[:24],
        message=sanitize_text(message, 2000),
        request_id=request_id_context.get()[:64],
        metadata_json=json.dumps(sanitize_metadata(metadata or {}), ensure_ascii=False),
    )
    db.add(event)
    return event


def serialize_audit_event(event: AuditEvent) -> dict:
    return {
        "id": event.id,
        "created_at": event.created_at.isoformat(),
        "actor": event.actor,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "outcome": event.outcome,
        "message": event.message,
        "request_id": event.request_id,
        "metadata": json.loads(event.metadata_json),
    }
