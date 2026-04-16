"""Synchronisation dynamique des commandes slash Discord.

Les commandes sont definies dans la DB (table slash_commands) et reconstruites
a chaque (re)demarrage du bot ou a chaque modif via l'API.

On utilise `CommandTree.add_command()` avec des `app_commands.Command` crees
dynamiquement. Toutes les commandes partagent le meme handler (`_execute_command`)
qui lit l'action dans la DB et appelle HA en consequence.
"""

from __future__ import annotations

import json
import logging

import discord
from discord import app_commands

from app.config import settings
from app.db.models import SlashCommand
from app.db.repositories import SlashCommandRepository
from app.ha import ha_client
from app.ha.client import HomeAssistantError

logger = logging.getLogger(__name__)


def _make_callback(command: SlashCommand):
    """Cree le callback d'une commande slash a partir de sa config DB.

    Chaque callback est une closure qui capture l'ID de la commande ;
    on re-lit la DB a l'execution pour toujours utiliser la derniere version.
    """
    cmd_id = command.id

    async def _callback(interaction: discord.Interaction) -> None:
        repo = SlashCommandRepository()
        cmd = await repo.get_by_id(cmd_id)
        if cmd is None or not cmd.enabled:
            await interaction.response.send_message(
                "Cette commande n'est plus disponible.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await _execute_action(cmd)
        except HomeAssistantError as exc:
            logger.error("Erreur execution commande %s : %s", cmd.name, exc)
            await interaction.followup.send(
                f"\u274c Erreur : {exc}", ephemeral=True
            )
            return

        await interaction.followup.send(cmd.response_message, ephemeral=True)

    return _callback


async def _execute_action(cmd: SlashCommand) -> None:
    """Execute l'action associee a une commande slash."""
    data: dict = {}
    if cmd.ha_data_json:
        try:
            data = json.loads(cmd.ha_data_json)
        except json.JSONDecodeError:
            logger.warning("ha_data_json invalide sur commande %s", cmd.name)

    if cmd.action_type == "service":
        if not cmd.ha_service or "." not in cmd.ha_service:
            raise HomeAssistantError(f"Service invalide : {cmd.ha_service}")
        domain, service = cmd.ha_service.split(".", 1)
        if cmd.ha_entity_id:
            data["entity_id"] = cmd.ha_entity_id
        await ha_client.call_service(domain, service, data)

    elif cmd.action_type == "script":
        # ha_entity_id est attendu sous la forme "script.mon_script"
        if not cmd.ha_entity_id or not cmd.ha_entity_id.startswith("script."):
            raise HomeAssistantError(f"Script invalide : {cmd.ha_entity_id}")
        script_name = cmd.ha_entity_id.split(".", 1)[1]
        await ha_client.call_service("script", script_name, data)

    elif cmd.action_type == "scene":
        if not cmd.ha_entity_id or not cmd.ha_entity_id.startswith("scene."):
            raise HomeAssistantError(f"Scene invalide : {cmd.ha_entity_id}")
        await ha_client.call_service(
            "scene", "turn_on", {"entity_id": cmd.ha_entity_id}
        )

    elif cmd.action_type == "notification":
        from app.bot.notifications import send_notification
        if not cmd.notification_slug:
            raise HomeAssistantError("Aucune notification associee")
        message = await send_notification(cmd.notification_slug)
        if message is None:
            raise HomeAssistantError(
                f"Echec d'envoi de la notification '{cmd.notification_slug}'"
            )

    else:
        raise HomeAssistantError(f"action_type inconnu : {cmd.action_type}")


async def sync_slash_commands(bot_: discord.Client) -> None:
    """(Re)construit et pousse toutes les slash commands vers Discord.

    On cible la guild configuree pour avoir une sync instantanee (sinon
    les commandes globales prennent jusqu'a 1h a se propager).
    """
    tree: app_commands.CommandTree = bot_.tree  # type: ignore[attr-defined]
    guild = discord.Object(id=settings.discord_guild_id)

    # Reset des commandes de la guild
    tree.clear_commands(guild=guild)

    repo = SlashCommandRepository()
    commands = await repo.list_all(only_enabled=True)

    for cmd in commands:
        dynamic_cmd = app_commands.Command(
            name=cmd.name,
            description=cmd.description[:100] or "Commande BotPanel",
            callback=_make_callback(cmd),
        )
        try:
            tree.add_command(dynamic_cmd, guild=guild)
        except app_commands.CommandAlreadyRegistered:
            logger.warning("Commande deja enregistree : %s", cmd.name)

    try:
        synced = await tree.sync(guild=guild)
        logger.info("%d commandes slash synchronisees sur la guild %s", len(synced), settings.discord_guild_id)
    except discord.HTTPException as exc:
        logger.error("Echec sync slash commands : %s", exc)
