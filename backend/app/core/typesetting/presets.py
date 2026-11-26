import json
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def load_presets() -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(TEMPLATE_DIR.glob("*.json"))
    ]


def get_preset(preset_id: str) -> dict:
    for preset in load_presets():
        if preset["id"] == preset_id:
            return preset
    raise ValueError("排版预设不存在")


def resolve_preset(preset_id: str, db) -> dict:
    from app.storage.models import Preset

    row = db.get(Preset, preset_id)
    if row is None:
        raise ValueError("排版预设不存在")
    if row.is_builtin:
        return {**get_preset(preset_id), "is_builtin": True}
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "platform_hint": row.platform_hint,
        "style_json": row.style_json,
        "is_builtin": False,
    }
