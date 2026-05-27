"""Routes proxy vers le bot Discord (lecture des channels accessibles)."""

from __future__ import annotations

import logging

import discord
from fastapi import APIRouter, Query

from app.bot.client import bot
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_guild() -> discord.Guild | None:
    if not bot.is_ready():
        return None
    guild = bot.get_guild(settings.discord_guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(settings.discord_guild_id)
        except discord.HTTPException as exc:
            logger.warning("Impossible de fetch la guild : %s", exc)
    return guild


@router.get("/channels")
async def list_text_channels() -> list[dict[str, str]]:
    """Liste les channels texte de la guild (pour autocompletion)."""
    guild = await _get_guild()
    if guild is None:
        return []
    result = [
        {"id": str(ch.id), "name": ch.name, "category": ch.category.name if ch.category else ""}
        for ch in guild.text_channels
    ]
    result.sort(key=lambda c: (c["category"], c["name"]))
    return result


@router.get("/forum-channels")
async def list_forum_channels() -> list[dict[str, str]]:
    """Liste les channels forum de la guild."""
    guild = await _get_guild()
    if guild is None:
        return []
    result = [
        {"id": str(ch.id), "name": ch.name, "category": ch.category.name if ch.category else ""}
        for ch in guild.channels
        if isinstance(ch, discord.ForumChannel)
    ]
    result.sort(key=lambda c: (c["category"], c["name"]))
    return result


@router.get("/forum-posts")
async def list_forum_posts(channel_id: str = Query(...)) -> list[dict]:
    """Liste les posts actifs (non archives) d'un channel forum."""
    if not bot.is_ready():
        return []
    try:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(channel_id))
    except (ValueError, discord.HTTPException):
        return []
    if not isinstance(channel, discord.ForumChannel):
        return []
    posts = [
        {"id": str(t.id), "name": t.name, "message_count": t.message_count or 0}
        for t in channel.threads
        if not t.archived
    ]
    posts.sort(key=lambda p: p["name"])
    return posts
