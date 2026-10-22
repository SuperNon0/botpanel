"""CRUD des blocs de monitoring (multi-blocs libres)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.db.models import MonitoringBlock, MonitoringBlockIn
from app.db.repositories import MonitoringRepository

router = APIRouter()
repo = MonitoringRepository()


async def _refresh_task(block_id: int) -> None:
    """Relance la task asyncio du bloc apres une modif."""
    from app.bot.client import bot
    from app.bot.monitoring import refresh_block_task
    if bot.is_ready():
        await refresh_block_task(bot, block_id)


@router.get("", response_model=list[MonitoringBlock])
async def list_blocks() -> list[MonitoringBlock]:
    return await repo.list_all()


@router.post("/preview")
async def preview_block(payload: MonitoringBlockIn) -> dict:
    """Rendu d'un brouillon de bloc avec les VRAIES valeurs Home Assistant.

    Rien n'est envoye sur Discord : sert a l'apercu live de l'editeur.
    """
    from app.bot.monitoring import render_block
    from app.ha import ha_client

    try:
        ha_ok = bool(await ha_client.ping())
    except Exception:  # noqa: BLE001
        ha_ok = False
    data = await render_block(MonitoringBlock(id=0, **payload.model_dump()))
    return {"ha_ok": ha_ok, **data}


@router.get("/{block_id}", response_model=MonitoringBlock)
async def get_block(block_id: int) -> MonitoringBlock:
    block = await repo.get_by_id(block_id)
    if block is None:
        raise HTTPException(404, "Bloc introuvable")
    return block


@router.post("", response_model=MonitoringBlock, status_code=201)
async def create_block(payload: MonitoringBlockIn) -> MonitoringBlock:
    block = await repo.create(payload)
    await _refresh_task(block.id)
    return block


@router.put("/{block_id}", response_model=MonitoringBlock)
async def update_block(block_id: int, payload: MonitoringBlockIn) -> MonitoringBlock:
    block = await repo.update(block_id, payload)
    if block is None:
        raise HTTPException(404, "Bloc introuvable")
    await _refresh_task(block_id)
    return block


@router.post("/{block_id}/refresh")
async def refresh_block(block_id: int) -> dict:
    """Met a jour tout de suite le message Discord du bloc."""
    from app.bot.client import bot
    from app.bot.monitoring import refresh_block_now

    block = await repo.get_by_id(block_id)
    if block is None:
        raise HTTPException(404, "Bloc introuvable")
    if not block.enabled:
        raise HTTPException(400, "Bloc desactive : active-le pour l'envoyer sur Discord")
    if not bot.is_ready():
        raise HTTPException(503, "Bot Discord non connecte")
    if not await refresh_block_now(bot, block_id):
        raise HTTPException(500, "Mise a jour impossible (voir l'historique)")
    return {"status": "ok"}


@router.post("/{block_id}/duplicate", response_model=MonitoringBlock, status_code=201)
async def duplicate_block(block_id: int) -> MonitoringBlock:
    """Duplique un bloc (cree desactive, pour ne pas poster un 2e message tout de suite)."""
    src = await repo.get_by_id(block_id)
    if src is None:
        raise HTTPException(404, "Bloc introuvable")
    payload = MonitoringBlockIn(
        **{**src.model_dump(exclude={"id", "message_id"}),
           "name": f"{src.name} (copie)"[:128], "enabled": False}
    )
    return await repo.create(payload)


@router.delete("/{block_id}", status_code=204, response_class=Response)
async def delete_block(block_id: int):
    # Stoppe la task avant suppression (on ignore les erreurs)
    try:
        from app.bot.client import bot
        from app.bot.monitoring import stop_block_task
        if bot.is_ready():
            await stop_block_task(block_id)
    except Exception:
        pass
    ok = await repo.delete(block_id)
    if not ok:
        raise HTTPException(404, "Bloc introuvable")
    return Response(status_code=204)
