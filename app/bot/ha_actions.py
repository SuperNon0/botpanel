"""Boutons d'action Home Assistant partages (commandes slash + monitoring).

Les notifications ont leurs boutons en table (avec un id) ; les commandes et
les blocs de monitoring les stockent en JSON et les identifient par leur
position. Ce module regroupe :
  - l'appel du service HA d'un bouton (`call_ha_button`) ;
  - la construction d'une View Discord persistante (`build_ha_buttons_view`).
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Iterable

import discord
from discord.ui import Button, View

from app.db.models import HaButton
from app.ha import ha_client
from app.ha.client import HomeAssistantError

logger = logging.getLogger(__name__)


DISCORD_STYLES: dict[str, discord.ButtonStyle] = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}


async def call_ha_service(
    service: str | None, entity_id: str | None = None, data_json: str | None = None
) -> None:
    """Appelle `domaine.action` avec entity_id + data JSON optionnels.

    Leve HomeAssistantError si le service est invalide ou si HA refuse.
    """
    if not service or "." not in service:
        raise HomeAssistantError(f"Service HA invalide : {service}")
    domain, srv = service.split(".", 1)

    data: dict = {}
    if data_json:
        try:
            parsed = json.loads(data_json)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            logger.warning("ha_data_json invalide ignore : %r", data_json)
    if entity_id:
        data["entity_id"] = entity_id

    await ha_client.call_service(domain, srv, data)


async def call_ha_button(button: HaButton) -> None:
    await call_ha_service(button.ha_service, button.ha_entity_id, button.ha_data_json)


def build_ha_buttons_view(
    buttons: Iterable[HaButton],
    custom_id: Callable[[int], str],
    extra: Iterable[Button] = (),
) -> View | None:
    """View persistante (timeout=None) : un bouton Discord par HaButton.

    `custom_id(idx)` donne l'identifiant stable du bouton n°idx (route par le
    dispatcher de `views.py`). `extra` ajoute des boutons systeme (ex.
    « Actualiser »). Renvoie None s'il n'y a aucun bouton (Discord refuse
    une View vide sur certains envois).
    """
    view = View(timeout=None)
    for idx, btn in enumerate(buttons):
        if len(view.children) >= 25:  # limite Discord
            break
        view.add_item(
            Button(
                style=DISCORD_STYLES.get(btn.style, discord.ButtonStyle.primary),
                label=btn.label[:80] or "Action",
                emoji=btn.emoji or None,
                custom_id=custom_id(idx),
            )
        )
    for item in extra:
        if len(view.children) >= 25:
            break
        view.add_item(item)
    return view if view.children else None
