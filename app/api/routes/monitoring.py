"""CRUD des blocs de monitoring."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.models import MonitoringBlock, MonitoringBlockIn
from app.db.repositories import MonitoringRepository

router = APIRouter()
repo = MonitoringRepository()


@router.get("", response_model=list[MonitoringBlock])
async def list_blocks() -> list[MonitoringBlock]:
    return await repo.list_all()


@router.get("/{block_type}", response_model=MonitoringBlock)
async def get_block(block_type: str) -> MonitoringBlock:
    block = await repo.get_by_type(block_type)
    if block is None:
        raise HTTPException(404, "Bloc introuvable")
    return block


@router.put("/{block_type}", response_model=MonitoringBlock)
async def update_block(block_type: str, payload: MonitoringBlockIn) -> MonitoringBlock:
    block = await repo.update(block_type, payload)
    if block is None:
        raise HTTPException(404, "Bloc introuvable")

    # Relance la task correspondante
    from app.bot.monitoring import refresh_block_task
    from app.bot.client import bot
    if bot.is_ready():
        await refresh_block_task(bot, block_type)
    return block
