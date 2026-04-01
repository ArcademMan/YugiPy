import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/settings", tags=["settings"])

SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "settings.json"


def _load() -> dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    return {}


def _save(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@router.get("")
def get_settings():
    """Get all user settings."""
    return _load()


@router.put("")
def update_settings(payload: dict):
    """Update user settings (merges with existing)."""
    current = _load()
    current.update(payload)
    _save(current)
    return current


@router.get("/{key}")
def get_setting(key: str):
    """Get a single setting by key."""
    data = _load()
    return {"key": key, "value": data.get(key)}


@router.put("/{key}")
def update_setting(key: str, payload: dict):
    """Update a single setting."""
    data = _load()
    data[key] = payload.get("value")
    _save(data)
    return {"key": key, "value": data[key]}
