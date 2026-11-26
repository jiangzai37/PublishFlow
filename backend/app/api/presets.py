import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import PresetCreate, PresetUpdate
from app.core.typesetting.presets import resolve_preset
from app.storage.database import get_db
from app.storage.models import Preset, PublishTask, SchedulePlan

router = APIRouter(tags=["presets"])


def serialize_preset(preset: Preset) -> dict:
    return {
        "id": preset.id,
        "name": preset.name,
        "description": preset.description,
        "platform_hint": preset.platform_hint,
        "style": json.loads(preset.style_json),
        "is_builtin": preset.is_builtin,
        "updated_at": preset.updated_at.isoformat() if preset.updated_at else None,
    }


@router.get("/presets")
def list_presets(db: Session = Depends(get_db)):
    presets = db.scalars(
        select(Preset).order_by(Preset.is_builtin.desc(), Preset.updated_at.desc())
    ).all()
    return [serialize_preset(preset) for preset in presets]


@router.get("/presets/{preset_id}")
def get_preset_detail(preset_id: str, db: Session = Depends(get_db)):
    try:
        preset = resolve_preset(preset_id, db)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {**preset, "style": json.loads(preset["style_json"])}


@router.post("/presets", status_code=201)
def create_preset(request: PresetCreate, db: Session = Depends(get_db)):
    preset = Preset(
        id=f"custom-{uuid.uuid4().hex}",
        name=request.name.strip(),
        description=request.description.strip(),
        platform_hint=request.platform_hint,
        style_json=request.style.model_dump_json(),
        is_builtin=False,
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return serialize_preset(preset)


@router.put("/presets/{preset_id}")
def update_preset(preset_id: str, request: PresetUpdate, db: Session = Depends(get_db)):
    preset = db.get(Preset, preset_id)
    if not preset:
        raise HTTPException(404, "排版预设不存在")
    if preset.is_builtin:
        raise HTTPException(409, "内置预设不可修改，请先复制为自定义模板。")
    preset.name = request.name.strip()
    preset.description = request.description.strip()
    preset.platform_hint = request.platform_hint
    preset.style_json = request.style.model_dump_json()
    db.commit()
    db.refresh(preset)
    return serialize_preset(preset)


@router.delete("/presets/{preset_id}", status_code=204)
def delete_preset(preset_id: str, db: Session = Depends(get_db)):
    preset = db.get(Preset, preset_id)
    if not preset:
        raise HTTPException(404, "排版预设不存在")
    if preset.is_builtin:
        raise HTTPException(409, "内置预设不可删除。")
    referenced = db.scalar(
        select(PublishTask.id).where(PublishTask.preset_id == preset_id).limit(1)
    )
    scheduled = db.scalar(
        select(SchedulePlan.id).where(SchedulePlan.preset_id == preset_id).limit(1)
    )
    if referenced or scheduled:
        raise HTTPException(409, "该模板仍被发布任务或调度计划引用，请先清理引用。")
    db.delete(preset)
    db.commit()
