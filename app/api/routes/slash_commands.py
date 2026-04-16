"""CRUD des commandes slash Discord."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.db.models import SlashCommand, SlashCommandIn
from app.db.repositories import SlashCommandRepository
from app.db.repositories.slash_commands import MAX_SLASH_COMMANDS

router = APIRouter()
repo = SlashCommandRepository()


async def _resync_discord() -> None:
    """Appelle la sync Discord apres toute modif."""
    from app.bot.client import bot
    from app.bot.slash_sync import sync_slash_commands
    if bot.is_ready():
        await sync_slash_commands(bot)


@router.get("", response_model=list[SlashCommand])
async def list_commands() -> list[SlashCommand]:
    return await repo.list_all()


@router.get("/quota")
async def get_quota() -> dict[str, int]:
    count = await repo.count()
    return {"used": count, "max": MAX_SLASH_COMMANDS, "remaining": MAX_SLASH_COMMANDS - count}


@router.post("", response_model=SlashCommand, status_code=201)
async def create_command(payload: SlashCommandIn) -> SlashCommand:
    count = await repo.count()
    if count >= MAX_SLASH_COMMANDS:
        raise HTTPException(
            400, f"Limite Discord atteinte ({MAX_SLASH_COMMANDS} commandes max)"
        )
    cmd = await repo.create(payload)
    await _resync_discord()
    return cmd


@router.put("/{cmd_id}", response_model=SlashCommand)
async def update_command(cmd_id: int, payload: SlashCommandIn) -> SlashCommand:
    cmd = await repo.update(cmd_id, payload)
    if cmd is None:
        raise HTTPException(404, "Commande introuvable")
    await _resync_discord()
    return cmd


@router.delete("/{cmd_id}", status_code=204, response_class=Response)
async def delete_command(cmd_id: int):
    ok = await repo.delete(cmd_id)
    if not ok:
        raise HTTPException(404, "Commande introuvable")
    await _resync_discord()
    return Response(status_code=204)
