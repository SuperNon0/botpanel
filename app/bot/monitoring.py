"""Taches periodiques de monitoring.

Chaque bloc active maintient un message Discord epingle qui est EDITE
(jamais supprime/recree) a chaque cycle. L'ID du message est persiste
dans la table monitoring_blocks pour survivre aux redemarrages.

Pour activer/desactiver a chaud depuis l'API :
  - update du bloc en DB
  - appel de `refresh_block_task(bot, block_type)`

Blocs supportes :
    temperature : 2 thermometres (config_json = {"sensors": [{"entity_id", "label"}]})
    power       : conso journaliere (config_json = {"entity_id": "sensor.conso_jour"})
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


# block_type -> asyncio.Task
_tasks: dict[str, asyncio.Task] = {}


# -------------------------------------------------------------------
# Construction des embeds
# -------------------------------------------------------------------
async def _build_temperature_embed(config: dict[str, Any]) -> discord.Embed:
    sensors = config.get("sensors", []) or []
    embed = discord.Embed(
        title="\U0001f321\ufe0f  Temperature & Humidite",
        color=0x4ADE80,
        timestamp=dt.datetime.now(dt.timezone.utc),
    )
    if not sensors:
        embed.description = "_Aucun capteur configure._"
        return embed

    for sensor in sensors:
        entity_id = sensor.get("entity_id")
        label = sensor.get("label") or entity_id or "Capteur"
        if not entity_id:
            embed.add_field(name=label, value="_entity_id manquant_", inline=True)
            continue
        state = await ha_client.get_state(entity_id)
        if state is None:
            embed.add_field(name=label, value="_indisponible_", inline=True)
            continue
        value = state.get("state", "?")
        unit = state.get("attributes", {}).get("unit_of_measurement", "")
        embed.add_field(
            name=label,
            value=f"**{value}** {unit}".strip(),
            inline=True,
        )
    embed.set_footer(text="Mise a jour")
    return embed


async def _build_power_embed(config: dict[str, Any]) -> discord.Embed:
    entity_id = config.get("entity_id")
    embed = discord.Embed(
        title="\u26a1  Consommation serveur",
        color=0xFFD93D,
        timestamp=dt.datetime.now(dt.timezone.utc),
    )
    if not entity_id:
        embed.description = "_Aucune entite configuree._"
        return embed

    state = await ha_client.get_state(entity_id)
    if state is None:
        embed.description = "_Entite indisponible._"
        return embed

    value = state.get("state", "?")
    unit = state.get("attributes", {}).get("unit_of_measurement", "")
    friendly = state.get("attributes", {}).get("friendly_name", entity_id)
    embed.add_field(name=friendly, value=f"**{value}** {unit}".strip(), inline=False)
    embed.set_footer(text="Mise a jour")
    return embed


async def _build_embed(block: MonitoringBlock) -> discord.Embed:
    try:
        config = json.loads(block.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    if block.block_type == "temperature":
        return await _build_temperature_embed(config)
    if block.block_type == "power":
        return await _build_power_embed(config)
    return discord.Embed(title=f"Bloc {block.block_type}", description="Type inconnu")


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
        logger.error("channel_id invalide bloc=%s : %r", block.block_type, channel_id)
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
            logger.info("Message monitoring introuvable pour %s, recreation.", block.block_type)

    # Creation d'un nouveau message
    embed = await _build_embed(block)
    try:
        message = await channel.send(embed=embed)  # type: ignore[union-attr]
    except discord.HTTPException as exc:
        logger.error("Echec envoi message monitoring %s : %s", block.block_type, exc)
        return None

    try:
        await message.pin(reason="BotPanel monitoring")
    except discord.HTTPException:
        logger.warning("Impossible d'epingler le message (permission manquante ?)")

    await repo.set_message_id(block.block_type, str(message.id))
    return message


# -------------------------------------------------------------------
# Boucle d'un bloc
# -------------------------------------------------------------------
async def _block_loop(bot_: discord.Client, block_type: str) -> None:
    repo = MonitoringRepository()
    logger.info("Demarrage task monitoring %s", block_type)
    while True:
        block = await repo.get_by_type(block_type)
        if block is None or not block.enabled:
            logger.info("Arret task monitoring %s (desactive).", block_type)
            return

        message = await _ensure_message(bot_, block)
        if message is not None:
            try:
                embed = await _build_embed(block)
                await message.edit(embed=embed)
            except discord.HTTPException as exc:
                logger.error("Edit du message monitoring %s echoue : %s", block_type, exc)
            except HomeAssistantError as exc:
                logger.warning("HA indisponible pour %s : %s", block_type, exc)

        await asyncio.sleep(max(30, block.interval_seconds))


# -------------------------------------------------------------------
# API du module (appele depuis client.py et les routes API)
# -------------------------------------------------------------------
async def refresh_block_task(bot_: discord.Client, block_type: str) -> None:
    """Redemarre la task d'un bloc (apres modif via l'API)."""
    existing = _tasks.get(block_type)
    if existing is not None and not existing.done():
        existing.cancel()
        try:
            await existing
        except (asyncio.CancelledError, Exception):
            pass

    repo = MonitoringRepository()
    block = await repo.get_by_type(block_type)
    if block is None or not block.enabled:
        _tasks.pop(block_type, None)
        return

    task = asyncio.create_task(_block_loop(bot_, block_type), name=f"monitor:{block_type}")
    _tasks[block_type] = task


async def start_monitoring_tasks(bot_: discord.Client) -> None:
    """Demarre les taches pour tous les blocs actives (appele dans setup_hook)."""
    repo = MonitoringRepository()
    blocks = await repo.list_all()
    for block in blocks:
        if block.enabled:
            await refresh_block_task(bot_, block.block_type)
    logger.info("%d tasks de monitoring actives", sum(1 for b in blocks if b.enabled))
