"""Settings globaux : presets de couleurs, channels et threads Discord."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.db.models import ChannelPreset, ColorPreset, NotificationThread
from app.db.repositories import SettingsRepository, ThreadRepository

router = APIRouter()
repo = SettingsRepository()
thread_repo = ThreadRepository()


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


@router.get("/home-url")
async def get_home_url() -> dict:
    url = await repo.get("home_url", "")
    return {"url": url or ""}


@router.put("/home-url")
async def set_home_url(payload: dict) -> dict:
    url = str(payload.get("url", "")).strip()
    await repo.set("home_url", url)
    return {"url": url}


# ----------------------------------------------------------------------
# Integration Home Assistant : cle API (cote humain / Parametres) + diagnostic
# ----------------------------------------------------------------------
@router.get("/integration")
async def get_integration() -> dict:
    """Etat de l'integration : cle API, HA joignable, derniere connexion HA."""
    from app.integration import ensure_api_key, get_last_seen
    from app.ha import ha_client
    from app.api.routes.integration import VERSION

    key = await ensure_api_key()  # cree la cle si elle n'existe pas encore
    try:
        ha_ok = await ha_client.ping()
    except Exception:  # noqa: BLE001
        ha_ok = False
    return {
        "api_key": key,
        "ha_reachable": bool(ha_ok),
        "last_seen": await get_last_seen(),  # ISO ou None
        "version": VERSION,
    }


@router.post("/integration/regenerate")
async def regenerate_integration_key() -> dict:
    """Regenere la cle API (l'ancienne cesse de fonctionner)."""
    from app.integration import regenerate_key
    return {"api_key": await regenerate_key()}


@router.get("/threads", response_model=list[NotificationThread])
async def get_threads() -> list[NotificationThread]:
    return await thread_repo.list_all()


@router.delete("/threads/{entry_id}", status_code=204, response_class=Response)
async def delete_thread(entry_id: int) -> Response:
    ok = await thread_repo.delete(entry_id)
    if not ok:
        raise HTTPException(404, "Thread introuvable")
    return Response(status_code=204)
