from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class LocalRequestGuardMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = set(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method", "GET").upper() in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if headers.get("sec-fetch-site") == "cross-site":
            await JSONResponse({"detail": "已拒绝跨站本地 API 请求。"}, status_code=403)(
                scope, receive, send
            )
            return
        origin = headers.get("origin")
        if origin:
            host = headers.get("host", "")
            same_origin = {
                f"http://{host}",
                f"https://{host}",
            }
            if origin not in self.allowed_origins and origin not in same_origin:
                await JSONResponse(
                    {"detail": "请求来源不属于受信任的本地工作台。"}, status_code=403
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)
