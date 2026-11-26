from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    accounts,
    analytics,
    assets,
    audit,
    content,
    drafts,
    media,
    presets,
    publish,
    schedules,
    tasks,
)
from app.config import PROJECT_DIR, get_settings
from app.core.audit_middleware import AuditMiddleware
from app.core.local_request_guard import LocalRequestGuardMiddleware
from app.queue_scheduler.manager import queue_manager
from app.storage.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    queue_manager.start()
    yield
    queue_manager.stop()


app = FastAPI(title="PublishFlow API", version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware)
app.add_middleware(LocalRequestGuardMiddleware, allowed_origins=settings.cors_list)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
for router in (
    content.router,
    drafts.router,
    media.router,
    assets.router,
    presets.router,
    accounts.router,
    publish.router,
    schedules.router,
    tasks.router,
    audit.router,
    analytics.router,
):
    app.include_router(router, prefix="/api")
app.mount("/media", StaticFiles(directory=settings.data_dir / "covers"), name="covers")
app.mount("/videos", StaticFiles(directory=settings.video_dir), name="videos")
app.mount("/assets", StaticFiles(directory=settings.asset_dir), name="assets")


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "version": "0.5.0",
        "mode": "local",
        "publishing_enabled": settings.publishing_enabled,
    }


frontend_dist = PROJECT_DIR / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
