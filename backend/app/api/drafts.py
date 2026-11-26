from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import DraftCreate, DraftReuseRequest, DraftUpdate, PreviewRequest
from app.config import get_settings
from app.core.compliance.validator import content_stats, validate_content
from app.core.content_gen.openai_provider import OpenAICompatibleProvider
from app.core.typesetting.engine import plain_text_from_html, render_article
from app.core.typesetting.presets import resolve_preset
from app.storage.database import get_db
from app.storage.models import Draft, PublishTask, SchedulePlan

router = APIRouter(tags=["drafts"])


def serialize_draft(draft: Draft) -> dict:
    return {
        "id": draft.id,
        "title": draft.title,
        "body": draft.body,
        "source": draft.source,
        "tags": [tag for tag in draft.tags.split(",") if tag],
        "cover_image": draft.cover_image,
        "content_type": draft.content_type,
        "video_path": draft.video_path,
        "video_duration": draft.video_duration,
        "video_width": draft.video_width,
        "video_height": draft.video_height,
        "video_partition": draft.video_partition,
        "video_collection": draft.video_collection,
        "status": draft.status,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


@router.post("/preview")
def preview_article(request: PreviewRequest, db: Session = Depends(get_db)):
    try:
        preset = resolve_preset(request.preset_id, db)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if request.style:
        preset = {**preset, "style_json": request.style.model_dump_json()}
    html = render_article(request.title, request.body, request.preset_id, request.cover_url, preset)
    return {
        "html": html,
        "preset_name": preset["name"],
        "stats": content_stats(request.title, request.body),
        "findings": validate_content(
            request.title,
            plain_text_from_html(html),
            get_settings().compliance_enabled,
            ",".join(request.tags),
        ),
    }


@router.get("/drafts")
def list_drafts(db: Session = Depends(get_db)):
    drafts = db.scalars(select(Draft).order_by(Draft.updated_at.desc())).all()
    return [serialize_draft(draft) for draft in drafts]


@router.post("/drafts", status_code=201)
def create_draft(request: DraftCreate, db: Session = Depends(get_db)):
    draft = Draft(
        title=request.title,
        body=request.body,
        source=request.source,
        tags=",".join(request.tags),
        cover_image=request.cover_image,
        content_type=request.content_type,
        video_path=request.video_path,
        video_duration=request.video_duration,
        video_width=request.video_width,
        video_height=request.video_height,
        video_partition=request.video_partition,
        video_collection=request.video_collection,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return serialize_draft(draft)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = db.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "草稿不存在")
    return serialize_draft(draft)


@router.put("/drafts/{draft_id}")
def update_draft(draft_id: int, request: DraftUpdate, db: Session = Depends(get_db)):
    draft = db.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "草稿不存在")
    draft.title = request.title
    draft.body = request.body
    draft.tags = ",".join(request.tags)
    draft.cover_image = request.cover_image
    draft.video_path = request.video_path
    draft.video_duration = request.video_duration
    draft.video_width = request.video_width
    draft.video_height = request.video_height
    draft.video_partition = request.video_partition
    draft.video_collection = request.video_collection
    db.commit()
    db.refresh(draft)
    return serialize_draft(draft)


@router.post("/drafts/{draft_id}/reuse", status_code=201)
async def reuse_draft(draft_id: int, request: DraftReuseRequest, db: Session = Depends(get_db)):
    source = db.get(Draft, draft_id)
    if not source:
        raise HTTPException(404, "草稿不存在")
    if source.content_type != "article":
        raise HTTPException(400, "当前仅支持文章草稿复用")
    title, body = source.title, source.body
    tags = [tag for tag in source.tags.split(",") if tag]
    if request.adapt:
        try:
            adapted = await OpenAICompatibleProvider().adapt(title, body, request.target_platform)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, "平台适配改写失败，请检查模型服务配置。") from exc
        title, body, tags = adapted.title, adapted.body, adapted.tags
    draft = Draft(
        title=title,
        body=body,
        source="reuse",
        tags=",".join(tags),
        cover_image=source.cover_image,
        content_type="article",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return serialize_draft(draft)


@router.delete("/drafts/{draft_id}", status_code=204)
def delete_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = db.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "草稿不存在")
    if db.scalar(select(PublishTask.id).where(PublishTask.draft_id == draft_id).limit(1)):
        raise HTTPException(409, "该草稿仍被发布任务引用，不能删除。")
    if db.scalar(select(SchedulePlan.id).where(SchedulePlan.draft_id == draft_id).limit(1)):
        raise HTTPException(409, "该草稿仍被调度计划引用，不能删除。")
    db.delete(draft)
    db.commit()
