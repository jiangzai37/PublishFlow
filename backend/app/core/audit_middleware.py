import logging
import uuid

from app.storage.audit import add_audit_event, request_id_context
from app.storage.database import SessionLocal

logger = logging.getLogger(__name__)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def audit_target(path: str) -> tuple[str, str, int | None]:
    parts = [part for part in path.split("/") if part]
    entity = parts[1] if len(parts) > 1 else "api"
    entity_id = next((int(part) for part in parts[2:] if part.isdigit()), None)
    if entity == "tasks":
        entity = "publish_task"
    return entity.rstrip("s") or "api", entity, entity_id


class AuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        if method in SAFE_METHODS or not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        token = request_id_context.set(request_id)
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            try:
                entity_type, resource, entity_id = audit_target(path)
                outcome = (
                    "success" if status_code < 400 else "denied" if status_code < 500 else "error"
                )
                with SessionLocal.begin() as db:
                    add_audit_event(
                        db,
                        action=f"{method.lower()}:{resource}",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        outcome=outcome,
                        message=f"{method} {path} -> {status_code}",
                        metadata={"method": method, "path": path, "status_code": status_code},
                    )
            except Exception:
                logger.exception("无法写入 API 审计日志")
            finally:
                request_id_context.reset(token)
