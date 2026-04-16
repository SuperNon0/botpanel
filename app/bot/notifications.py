"""Construction et envoi des notifications Discord."""

from __future__ import annotations

import datetime as dt
import logging

import discord

from app.bot.client import bot
from app.bot.views import build_notification_view
from app.config import settings
from app.db.models import Notification
from app.db.repositories import NotificationRepository

logger = logging.getLogger(__name__)


STYLE_TO_COLOR: dict[str, int] = {
    "yellow": 0xFFD93D,
    "green": 0x4ADE80,
    "purple": 0x8B5CF6,
    "orange": 0xF59E0B,
    "red": 0xEF4444,
}


def build_embed(notif: Notification) -> discord.Embed:
    """Construit l'embed Discord d'une notification."""
    embed = discord.Embed(
        title=notif.title,
        description=notif.message,
        color=notif.color,
    )
    if notif.icon_url:
        embed.set_thumbnail(url=notif.icon_url)
    if notif.footer:
        embed.set_footer(text=notif.footer)
    if notif.show_timestamp:
        embed.timestamp = dt.datetime.now(dt.timezone.utc)
    return embed


async def _resolve_channel(channel_id: str) -> discord.abc.Messageable | None:
    """Recupere un channel Discord par son ID (cache ou fetch)."""
    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        logger.error("channel_id invalide : %r", channel_id)
        return None
    channel = bot.get_channel(cid)
    if channel is None:
        try:
            channel = await bot.fetch_channel(cid)
        except discord.HTTPException as exc:
            logger.error("Impossible de fetch le channel %s : %s", cid, exc)
            return None
    return channel  # type: ignore[return-value]


async def send_notification(slug: str) -> discord.Message | None:
    """Envoie la notification identifiee par `slug` dans son channel Discord.

    Retourne le message envoye ou None si echec.
    """
    repo = NotificationRepository()
    notif = await repo.get_by_slug(slug)
    if notif is None:
        logger.warning("Notification inconnue : %s", slug)
        return None

    channel_id = notif.channel_id or str(settings.discord_default_channel_id)
    channel = await _resolve_channel(channel_id)
    if channel is None:
        return None

    embed = build_embed(notif)
    view = build_notification_view(notif)
    try:
        message = await channel.send(embed=embed, view=view)
    except discord.HTTPException as exc:
        logger.error("Echec envoi notification %s : %s", slug, exc)
        return None

    logger.info("Notification '%s' envoyee dans #%s (msg=%s)", slug, channel_id, message.id)
    return message
