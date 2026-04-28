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
