"""Construction et envoi des notifications Discord."""

from __future__ import annotations

import datetime as dt
import logging
import re

import discord

from app.bot.client import bot
from app.bot.views import build_notification_view
from app.config import settings
from app.db.models import Notification
from app.db.repositories import LogRepository, NotificationRepository
from app.ha import ha_client

logger = logging.getLogger(__name__)


STYLE_TO_COLOR: dict[str, int] = {
    "yellow": 0xFFD93D,
    "green": 0x4ADE80,
    "purple": 0x8B5CF6,
    "orange": 0xF59E0B,
    "red": 0xEF4444,
}


# ----------------------------------------------------------------------
# Resolution des placeholders {state:..} {attr:..} {unit:..}
# ----------------------------------------------------------------------
# Syntaxe :
#   {state:sensor.xxx}            -> etat brut (str(state))
#   {state:sensor.xxx|--}         -> avec fallback si indisponible
#   {attr:sensor.xxx:friendly_name}
#   {attr:sensor.xxx:friendly_name|--}
#   {unit:sensor.xxx}             -> unit_of_measurement
PLACEHOLDER_RE = re.compile(
    r"\{(state|attr|unit):([a-zA-Z0-9_.]+)(?::([a-zA-Z0-9_]+))?(?:\|([^}]*))?\}"
)


async def _resolve_template(template: str) -> str:
    """Remplace les placeholders {state:..} etc. dans une string."""
    if not template or "{" not in template:
        return template

    # On collecte d'abord toutes les entites a fetch (dedoublonne)
    entities: dict[str, dict | None] = {}
    for match in PLACEHOLDER_RE.finditer(template):
        entity_id = match.group(2)
        if entity_id not in entities:
            entities[entity_id] = None  # placeholder

    # Fetch en parallele aurait ete plus rapide, mais on garde simple ici.
    for entity_id in entities:
        try:
            entities[entity_id] = await ha_client.get_state(entity_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HA get_state(%s) a echoue : %s", entity_id, exc)
            entities[entity_id] = None

    def replace(match: re.Match) -> str:
        kind = match.group(1)
        entity_id = match.group(2)
        attr = match.group(3)
        fallback = match.group(4) if match.group(4) is not None else "?"
        state = entities.get(entity_id)
        if state is None:
            return fallback
        if kind == "state":
            return str(state.get("state", fallback))
        if kind == "unit":
            return str(state.get("attributes", {}).get("unit_of_measurement", fallback))
        if kind == "attr":
            if not attr:
                return fallback
            value = state.get("attributes", {}).get(attr)
            return str(value) if value is not None else fallback
        return fallback

    return PLACEHOLDER_RE.sub(replace, template)


# ----------------------------------------------------------------------
# Construction de l'embed
# ----------------------------------------------------------------------
_FR_MONTHS = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


def _format_fr_datetime(now: dt.datetime) -> str:
    """Renvoie une date FR absolue : '28 avril 2026 a 14:05'.

    On evite le rendu Discord auto ('aujourd'hui a ...') en n'utilisant
    pas `embed.timestamp` mais en injectant la date directement dans le footer.
    """
    return f"{now.day} {_FR_MONTHS[now.month - 1]} {now.year} a {now:%H:%M}"


async def build_embed(notif: Notification) -> discord.Embed:
    """Construit l'embed Discord d'une notification (resolution des placeholders incluse)."""
    description = await _resolve_template(notif.message)

    embed = discord.Embed(
        title=notif.title,
        description=description,
        color=notif.color,
    )
    if notif.icon_url:
        embed.set_thumbnail(url=notif.icon_url)

    # Footer = footer texte + (optionnel) date absolue.
    footer_parts: list[str] = []
    if notif.footer:
        footer_parts.append(notif.footer)
    if notif.show_timestamp:
        footer_parts.append(_format_fr_datetime(dt.datetime.now()))
    if footer_parts:
        embed.set_footer(text=" \u00b7 ".join(footer_parts))

    # Fields custom (resolution des placeholders dans value)
    for fld in sorted(notif.fields, key=lambda f: (f.position, f.id or 0)):
        value = await _resolve_template(fld.value_template)
        embed.add_field(name=fld.name, value=value or "\u200b", inline=fld.inline)

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
    """Envoie la notification identifiee par `slug` dans son channel Discord."""
    repo = NotificationRepository()
    notif = await repo.get_by_slug(slug)
    if notif is None:
        logger.warning("Notification inconnue : %s", slug)
        return None
    return await send_notification_object(notif)


async def send_notification_object(notif: Notification) -> discord.Message | None:
    """Envoie une notification (deja chargee) dans son channel Discord.

    Sert au test depuis l'editeur (notif non persistee) et a l'envoi normal.
    """
    channel_id = notif.channel_id or str(settings.discord_default_channel_id)
    channel = await _resolve_channel(channel_id)
    log_repo = LogRepository()

    if channel is None:
        await log_repo.add(
            kind="send",
            notification_id=notif.id or None,
            notification_slug=notif.slug,
            channel_id=channel_id,
            success=False,
            detail=f"Channel {channel_id} introuvable",
        )
        return None

    embed = await build_embed(notif)
    # Une view persistante n'est possible que si la notif est en DB
    # (les boutons sont identifies par notif.id + button.id).
    view = build_notification_view(notif) if notif.id else None
    try:
        message = await channel.send(embed=embed, view=view) if view else await channel.send(embed=embed)
    except discord.HTTPException as exc:
        logger.error("Echec envoi notification %s : %s", notif.slug, exc)
        await log_repo.add(
            kind="send",
            notification_id=notif.id or None,
            notification_slug=notif.slug,
            channel_id=channel_id,
            success=False,
            detail=str(exc)[:300],
        )
        return None

    logger.info(
        "Notification '%s' envoyee dans #%s (msg=%s)%s",
        notif.slug, channel_id, message.id,
        "" if notif.id else " [test ephemere]",
    )
    await log_repo.add(
        kind="send",
        notification_id=notif.id or None,
        notification_slug=notif.slug,
        channel_id=channel_id,
        message_id=str(message.id),
        success=True,
        detail="ephemere (test)" if not notif.id else None,
    )
    return message
