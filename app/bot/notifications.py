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
    """Remplace les placeholders dans une string.

    Deux syntaxes supportees :
      1. Syntaxe BotPanel (rapide, no round-trip si pas utilisee) :
         {state:sensor.x}  {state:sensor.x|--}
         {attr:sensor.x:friendly_name}  {unit:sensor.x}
      2. Syntaxe Jinja Home Assistant (envoyee a /api/template) :
         {{ states('sensor.x') }}
         {{ state_attr('sensor.x', 'attr') }}
         {% if ... %}...{% endif %}

    Si les deux sont presentes : on resout d'abord les placeholders BotPanel,
    puis on envoie le resultat a HA pour rendre le Jinja restant.
    """
    if not template or "{" not in template:
        return template

    # 1) Resolution des placeholders BotPanel (rapide, fetch en local)
    if PLACEHOLDER_RE.search(template):
        entities: dict[str, dict | None] = {}
        for match in PLACEHOLDER_RE.finditer(template):
            entity_id = match.group(2)
            if entity_id not in entities:
                entities[entity_id] = None

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

        template = PLACEHOLDER_RE.sub(replace, template)

    # 2) Si la string contient encore du Jinja HA, on demande a HA de la rendre.
    if "{{" in template or "{%" in template:
        try:
            template = await ha_client.render_template(template)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rendu Jinja HA echoue : %s", exc)

    return template


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


async def _get_or_create_thread(
    channel: discord.TextChannel, group_name: str
) -> discord.Thread:
    """Retourne le thread Discord actif pour ce groupe, ou en cree un nouveau.

    Le thread_id est persiste en DB pour eviter un scan Discord a chaque envoi.
    Si le thread a ete archive ou supprime, il est recrée automatiquement.
    """
    from app.db.repositories.threads import ThreadRepository

    repo = ThreadRepository()
    stored_id = await repo.get_thread_id(group_name, str(channel.id))

    if stored_id:
        try:
            existing = await bot.fetch_channel(int(stored_id))
            if isinstance(existing, discord.Thread):
                if existing.archived:
                    await existing.edit(archived=False)
                return existing
        except (discord.NotFound, discord.HTTPException):
            pass  # thread supprime, on en cree un nouveau

    thread = await channel.create_thread(
        name=group_name,
        auto_archive_duration=10080,  # 7 jours
        type=discord.ChannelType.public_thread,
    )
    await repo.upsert(group_name, str(channel.id), str(thread.id))
    logger.info("Thread '%s' cree (id=%s) dans #%s", group_name, thread.id, channel.id)
    return thread


async def send_notification_object(notif: Notification) -> discord.Message | None:
    """Envoie une notification (deja chargee) dans son channel Discord.

    Si la notification a un `group_name` et un ID persiste, l'envoi se fait
    dans un thread Discord portant ce nom (cree ou recupere automatiquement).
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

    # Routing vers un thread si group_name est defini et la notif est persistee.
    destination: discord.abc.Messageable = channel
    if notif.group_name and notif.id and isinstance(channel, discord.TextChannel):
        try:
            destination = await _get_or_create_thread(channel, notif.group_name)
        except discord.HTTPException as exc:
            logger.warning(
                "Impossible de creer/recuperer le thread '%s' : %s — envoi dans le channel",
                notif.group_name, exc,
            )

    embed = await build_embed(notif)
    view = build_notification_view(notif)  # gere aussi le mode preview
    try:
        message = await destination.send(embed=embed, view=view)
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

    in_thread = isinstance(destination, discord.Thread)
    logger.info(
        "Notification '%s' envoyee dans %s%s (msg=%s)%s",
        notif.slug,
        "thread " + notif.group_name if in_thread else "#" + channel_id,
        "" if in_thread else "",
        message.id,
        "" if notif.id else " [test ephemere]",
    )
    await log_repo.add(
        kind="send",
        notification_id=notif.id or None,
        notification_slug=notif.slug,
        channel_id=channel_id,
        message_id=str(message.id),
        success=True,
        detail=f"thread:{notif.group_name}" if in_thread else ("ephemere (test)" if not notif.id else None),
    )
    return message
