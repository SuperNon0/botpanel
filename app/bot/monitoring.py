"""Taches periodiques de monitoring (multi-blocs).

Chaque bloc actif maintient un message Discord epingle qui est EDITE
(jamais supprime/recree) a chaque cycle. L'ID du message est persiste
dans la table monitoring_blocks pour survivre aux redemarrages.

Pour activer/desactiver/modifier a chaud depuis l'API :
  - update du bloc en DB
  - appel de `refresh_block_task(bot, block_id)`
  - ou `stop_block_task(block_id)` lors d'une suppression

Structure attendue de `config_json` :
    {
      "fields": [
        {
          "label": "Temperature",
          "icon":  "\U0001f321\ufe0f",
          "entity_id": "sensor.temp_salon",
          "attribute": null,           # ou un nom d'attribut HA
          "suffix": "\u00b0C",
          "inline": true
        },
        ...
      ]
    }
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from typing import Any, Optional

import discord

from app.config import settings
from app.db.models import MonitoringBlock
from app.db.repositories import MonitoringRepository
from app.ha import ha_client
from app.ha.client import HomeAssistantError

logger = logging.getLogger(__name__)


# block_id -> asyncio.Task
_tasks: dict[int, asyncio.Task] = {}


# -------------------------------------------------------------------
# Construction des embeds
# -------------------------------------------------------------------
async def _resolve_field_value(field: dict[str, Any]) -> str:
    """Resout la valeur a afficher pour un field d'un bloc monitoring."""
    entity_id = field.get("entity_id")
    suffix = field.get("suffix") or ""
    attribute = field.get("attribute")
    if not entity_id:
        return "_entity_id manquant_"

    state = await ha_client.get_state(entity_id)
    if state is None:
        return "_indisponible_"

    if attribute:
        value = state.get("attributes", {}).get(attribute)
        if value is None:
            return "_attribut absent_"
    else:
        value = state.get("state", "?")

    text = f"**{value}**"
    if suffix:
        text = f"{text} {suffix}"
    return text


async def _build_embed(block: MonitoringBlock) -> discord.Embed:
    try:
        config = json.loads(block.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    title = block.name or "Monitoring"
    if block.icon:
        title = f"{block.icon}  {title}"

    embed = discord.Embed(
        title=title,
        color=block.color,
        timestamp=dt.datetime.now(dt.timezone.utc),
    )

    fields = config.get("fields") or []
    if not fields:
        embed.description = "_Aucun champ configure._"
    else:
        for field in fields:
            label = field.get("label") or field.get("entity_id") or "Field"
            icon = field.get("icon")
            if icon:
                label = f"{icon} {label}"
            value = await _resolve_field_value(field)
            embed.add_field(
                name=label,
                value=value,
                inline=bool(field.get("inline", True)),
            )

    embed.set_footer(text=block.footer or "Mise a jour")
    return embed


# -------------------------------------------------------------------
# Resolution du message a editer (creation si absent)
# -------------------------------------------------------------------
async def _ensure_message(
    bot_: discord.Client, block: MonitoringBlock
) -> Optional[discord.Message]:
    channel_id = block.channel_id or str(settings.discord_monitoring_channel_id)
    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        logger.error("channel_id invalide bloc=%s : %r", block.id, channel_id)
        return None

    channel = bot_.get_channel(cid)
    if channel is None:
        try:
            channel = await bot_.fetch_channel(cid)
        except discord.HTTPException as exc:
            logger.error("Impossible de fetch le channel %s : %s", cid, exc)
            return None

    repo = MonitoringRepository()

    # On tente de recuperer le message existant
    if block.message_id:
        try:
            return await channel.fetch_message(int(block.message_id))  # type: ignore[union-attr]
        except (discord.NotFound, discord.HTTPException):
            logger.info("Message monitoring introuvable pour bloc %s, recreation.", block.id)

    # Creation d'un nouveau message
    embed = await _build_embed(block)
    try:
        message = await channel.send(embed=embed)  # type: ignore[union-attr]
    except discord.HTTPException as exc:
        logger.error("Echec envoi message monitoring %s : %s", block.id, exc)
        return None

    try:
        await message.pin(reason="BotPanel monitoring")
    except discord.HTTPException:
        logger.warning("Impossible d'epingler le message (permission manquante ?)")

    await repo.set_message_id(block.id, str(message.id))
    return message


# -------------------------------------------------------------------
# Boucle d'un bloc
# -------------------------------------------------------------------
async def _block_loop(bot_: discord.Client, block_id: int) -> None:
    repo = MonitoringRepository()
    logger.info("Demarrage task monitoring bloc=%s", block_id)
    while True:
        block = await repo.get_by_id(block_id)
        if block is None or not block.enabled:
            logger.info("Arret task monitoring bloc=%s (desactive ou supprime).", block_id)
            return

        message = await _ensure_message(bot_, block)
        if message is not None:
            try:
                embed = await _build_embed(block)
                await message.edit(embed=embed)
            except discord.HTTPException as exc:
                logger.error("Edit du message monitoring %s echoue : %s", block_id, exc)
            except HomeAssistantError as exc:
                logger.warning("HA indisponible pour bloc %s : %s", block_id, exc)

        await asyncio.sleep(max(30, block.interval_seconds))


# -------------------------------------------------------------------
# API du module (appele depuis client.py et les routes API)
# -------------------------------------------------------------------
async def stop_block_task(block_id: int) -> None:
    """Stoppe la task d'un bloc (avant suppression ou desactivation)."""
    existing = _tasks.pop(block_id, None)
    if existing is not None and not existing.done():
        existing.cancel()
        try:
            await existing
        except (asyncio.CancelledError, Exception):
            pass


async def refresh_block_task(bot_: discord.Client, block_id: int) -> None:
    """Redemarre la task d'un bloc (apres modif via l'API)."""
    await stop_block_task(block_id)

    repo = MonitoringRepository()
    block = await repo.get_by_id(block_id)
    if block is None or not block.enabled:
        return

    task = asyncio.create_task(_block_loop(bot_, block_id), name=f"monitor:{block_id}")
    _tasks[block_id] = task


async def start_monitoring_tasks(bot_: discord.Client) -> None:
    """Demarre les taches pour tous les blocs actives (appele dans setup_hook)."""
    repo = MonitoringRepository()
    blocks = await repo.list_all()
    for block in blocks:
        if block.enabled:
            await refresh_block_task(bot_, block.id)
    logger.info("%d tasks de monitoring actives", sum(1 for b in blocks if b.enabled))
