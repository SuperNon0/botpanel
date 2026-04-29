"""Settings globaux : presets de couleurs et de channels."""

from __future__ import annotations

from fastapi import APIRouter

from app.db.models import ChannelPreset, ColorPreset
from app.db.repositories import SettingsRepository

router = APIRouter()
repo = SettingsRepository()


@router.get("/colors", response_model=list[ColorPreset])
async def get_color_presets() -> list[ColorPreset]:
    raw = await repo.get_color_presets()
    return [ColorPreset(**c) for c in raw]


@router.put("/colors", response_model=list[ColorPreset])
async def set_color_presets(payload: list[ColorPreset]) -> list[ColorPreset]:
    await repo.set("color_presets", [c.model_dump() for c in payload])
    return payload


@router.get("/channels", response_model=list[ChannelPreset])
async def get_channel_presets() -> list[ChannelPreset]:
    raw = await repo.get_channel_presets()
    return [ChannelPreset(**c) for c in raw]


@router.put("/channels", response_model=list[ChannelPreset])
async def set_channel_presets(payload: list[ChannelPreset]) -> list[ChannelPreset]:
    await repo.set("channel_presets", [c.model_dump() for c in payload])
    return payload
