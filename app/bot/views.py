"""Vues Discord et boutons persistants pour les notifications.

Strategie pour le timeout 15 min des boutons : toutes les Views utilisent
`timeout=None` et chaque bouton a un `custom_id` stable encodant le type d'action
et l'ID cible en base. Un handler unique (`PersistentDispatcher`) est enregistre
au demarrage via `bot.add_view(...)` pour intercepter les clics meme apres
redemarrage du bot.
"""

from __future__ import annotations

import asyncio
import json
import logging

import discord
from discord.ui import Button, View

from app.db.models import Notification, NotificationButton
from app.db.repositories import LogRepository, NotificationRepository
from app.ha import ha_client

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Helpers custom_id
# -----------------------------------------------------------------
#   Format : "bp:<action>:<notif_id>[:<button_id>]"
#     - bp:del:<notif_id>             -> supprime le message
#     - bp:snz:<notif_id>             -> re-envoie la notif apres N minutes
#     - bp:btn:<notif_id>:<button_id> -> execute le service HA du bouton custom
# -----------------------------------------------------------------
CUSTOM_ID_PREFIX = "bp"


def _cid_delete(notif_id: int) -> str:
    return f"{CUSTOM_ID_PREFIX}:del:{notif_id}"


def _cid_snooze(notif_id: int) -> str:
    return f"{CUSTOM_ID_PREFIX}:snz:{notif_id}"


def _cid_custom(notif_id: int, button_id: int) -> str:
    return f"{CUSTOM_ID_PREFIX}:btn:{notif_id}:{button_id}"


DISCORD_STYLES: dict[str, discord.ButtonStyle] = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}


# -----------------------------------------------------------------
# View construite a l'envoi d'une notification
# -----------------------------------------------------------------
def build_notification_view(notif: Notification) -> View:
    """Cree une View persistante avec les boutons configures."""
    view = View(timeout=None)

    for btn in notif.buttons:
        assert btn.id is not None, "button must be persisted"
        view.add_item(
            Button(
                style=DISCORD_STYLES.get(btn.style, discord.ButtonStyle.primary),
                label=btn.label,
                emoji=btn.emoji or None,
                custom_id=_cid_custom(notif.id, btn.id),
            )
        )

    if notif.snooze_button:
        view.add_item(
            Button(
                style=discord.ButtonStyle.secondary,
                label=f"Snooze {notif.snooze_minutes}min",
                emoji="\U0001f514",  # bell
                custom_id=_cid_snooze(notif.id),
            )
        )

    if notif.delete_button:
        view.add_item(
            Button(
                style=discord.ButtonStyle.danger,
                label="Supprimer",
                emoji="\U0001f5d1",  # wastebasket
                custom_id=_cid_delete(notif.id),
            )
        )

    return view


# -----------------------------------------------------------------
# Dispatcher persistant
# -----------------------------------------------------------------
class PersistentDispatcher(View):
    """View enregistree une fois au boot pour router tous les clics BotPanel.

    Elle ne contient aucun bouton "en dur" ; elle utilise `interaction_check`
    sur une vue vide — en pratique, discord.py route par custom_id des qu'on
    enregistre une view persistante avec un bouton qui a un custom_id et
    timeout=None. On s'appuie donc sur un routing manuel via on_interaction.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)


async def _log_click(
    interaction: discord.Interaction,
    *,
    notif_id: int,
    kind: str,
    button_label: str,
    detail: str | None = None,
    success: bool = True,
) -> None:
    user = interaction.user
    await LogRepository().add(
        kind=kind,
        notification_id=notif_id,
        channel_id=str(interaction.channel_id) if interaction.channel_id else None,
        message_id=str(interaction.message.id) if interaction.message else None,
        user_id=str(user.id) if user else None,
        user_name=str(user) if user else None,
        button_label=button_label,
        detail=detail,
        success=success,
    )


async def _handle_delete(interaction: discord.Interaction, notif_id: int) -> None:
    if interaction.message is None:
        await interaction.response.send_message("Message introuvable.", ephemeral=True)
        return
    try:
        await interaction.message.delete()
        await _log_click(interaction, notif_id=notif_id, kind="delete", button_label="Supprimer")
    except discord.HTTPException as exc:
        logger.error("Echec suppression message : %s", exc)
        await _log_click(
            interaction, notif_id=notif_id, kind="delete",
            button_label="Supprimer", detail=str(exc)[:200], success=False,
        )
        await interaction.response.send_message(
            "Impossible de supprimer le message.", ephemeral=True
        )


async def _handle_snooze(interaction: discord.Interaction, notif_id: int) -> None:
    repo = NotificationRepository()
    notif = await repo.get_by_id(notif_id)
    if notif is None:
        await interaction.response.send_message(
            "Notification introuvable.", ephemeral=True
        )
        return

    delay = max(1, notif.snooze_minutes) * 60

    # On supprime la notif courante et on la re-envoie apres le delai.
    try:
        if interaction.message:
            await interaction.message.delete()
    except discord.HTTPException:
        pass

    await interaction.response.send_message(
        f"Snooze : je te repingue dans {notif.snooze_minutes} min.",
        ephemeral=True,
    )
    await _log_click(
        interaction, notif_id=notif_id, kind="snooze",
        button_label=f"Snooze {notif.snooze_minutes}min",
        detail=f"Re-envoi dans {notif.snooze_minutes} min",
    )

    async def _resend() -> None:
        await asyncio.sleep(delay)
        from app.bot.notifications import send_notification  # import tardif
        await send_notification(notif.slug)

    asyncio.create_task(_resend())


async def _handle_custom_button(
    interaction: discord.Interaction, notif_id: int, button_id: int
) -> None:
    repo = NotificationRepository()
    notif = await repo.get_by_id(notif_id)
    if notif is None:
        await interaction.response.send_message(
            "Notification introuvable.", ephemeral=True
        )
        return

    target: NotificationButton | None = next(
        (b for b in notif.buttons if b.id == button_id), None
    )
    if target is None:
        await interaction.response.send_message(
            "Bouton introuvable.", ephemeral=True
        )
        return

    # On construit la data HA (entity_id + data_json eventuel).
    service = target.ha_service
    if "." not in service:
        await interaction.response.send_message(
            f"Service HA invalide : {service}", ephemeral=True
        )
        return
    domain, srv = service.split(".", 1)

    data: dict = {}
    if target.ha_data_json:
        try:
            data = json.loads(target.ha_data_json)
        except json.JSONDecodeError:
            logger.warning("ha_data_json invalide sur bouton %s", button_id)
    if target.ha_entity_id:
        data["entity_id"] = target.ha_entity_id

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await ha_client.call_service(domain, srv, data)
    except Exception as exc:  # HomeAssistantError remonte ici
        logger.error("Erreur appel HA depuis bouton : %s", exc)
        await _log_click(
            interaction, notif_id=notif_id, kind="button",
            button_label=target.label,
            detail=f"{service} -> {exc}"[:300], success=False,
        )
        await interaction.followup.send(
            f"\u274c Erreur : {exc}", ephemeral=True
        )
        return

    await _log_click(
        interaction, notif_id=notif_id, kind="button",
        button_label=target.label, detail=service,
    )
    await interaction.followup.send(
        f"\u2705 {target.label} execute.", ephemeral=True
    )


async def dispatch_interaction(interaction: discord.Interaction) -> bool:
    """Route une interaction vers le handler adequat.

    Retourne True si l'interaction a ete prise en charge par BotPanel.
    """
    if interaction.type != discord.InteractionType.component:
        return False
    custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
    if not custom_id.startswith(f"{CUSTOM_ID_PREFIX}:"):
        return False

    parts = custom_id.split(":")
    # parts: ["bp", action, notif_id, (button_id)?]
    if len(parts) < 3:
        return False
    action = parts[1]
    try:
        notif_id = int(parts[2])
    except ValueError:
        return False

    if action == "del":
        await _handle_delete(interaction, notif_id)
        return True
    if action == "snz":
        await _handle_snooze(interaction, notif_id)
        return True
    if action == "btn" and len(parts) == 4:
        try:
            button_id = int(parts[3])
        except ValueError:
            return False
        await _handle_custom_button(interaction, notif_id, button_id)
        return True
    return False


async def register_persistent_views(bot_: discord.Client) -> None:
    """Enregistre le listener d'interactions au boot du bot.

    discord.py 2.x peut router les components via add_view ; on prefere ici
    un listener global pour ne pas avoir a reconstruire toutes les Views au
    boot (les notifs sont dynamiques).
    """
    async def _listener(interaction: discord.Interaction) -> None:
        try:
            await dispatch_interaction(interaction)
        except Exception:
            logger.exception("Erreur dans dispatch_interaction")

    bot_.add_listener(_listener, name="on_interaction")
    logger.info("Dispatcher BotPanel enregistre sur on_interaction")
