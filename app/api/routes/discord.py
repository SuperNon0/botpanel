"""Routes proxy vers le bot Discord (lecture des channels accessibles)."""

from __future__ import annotations

import logging

import discord
from fastapi import APIRouter

from app.bot.client import bot
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/channels")
async def list_text_channels() -> list[dict[str, str]]:
    """Liste les channels texte de la guild configuree.

    Renvoyee dans un format compatible autocomplete : {id, name, category}.
    Si le bot n'est pas pret ou la guild introuvable, renvoie une liste vide.
    """
    if not bot.is_ready():
        return []

    guild = bot.get_guild(settings.discord_guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(settings.discord_guild_id)
        except discord.HTTPException as exc:
            logger.warning("Impossible de fetch la guild : %s", exc)
            return []

    result: list[dict[str, str]] = []
    for ch in guild.text_channels:
        result.append({
            "id": str(ch.id),
            "name": ch.name,
            "category": ch.category.name if ch.category else "",
        })
    result.sort(key=lambda c: (c["category"], c["name"]))
    return result
