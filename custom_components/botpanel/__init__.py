"""Intégration BotPanel pour Home Assistant.

Expose les notifications BotPanel sous forme de boutons + une action
`botpanel.envoyer`, et des capteurs d'état. Déclenchement PAR ID uniquement :
Home Assistant ne configure jamais rien, tout le contenu reste sur BotPanel.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BotpanelApi
from .const import CONF_API_KEY, CONF_BASE_URL, DOMAIN, PLATFORMS, SERVICE_ENVOYER
from .coordinator import BotpanelCoordinator

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("notification"): cv.entity_id,
        vol.Optional("slug"): cv.string,
        vol.Optional("id"): vol.Coerce(int),
    }
)


def _notif_id_from_entity(hass: HomeAssistant, entity_id: str) -> int | None:
    """Retrouve l'id de la notif à partir d'un bouton BotPanel choisi dans la liste."""
    ent = er.async_get(hass).async_get(entity_id)
    if ent and ent.unique_id and "_notif_" in ent.unique_id:
        try:
            return int(ent.unique_id.rsplit("_notif_", 1)[1])
        except ValueError:
            return None
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place l'intégration à partir d'une entrée de configuration."""
    session = async_get_clientsession(hass)
    api = BotpanelApi(session, entry.data[CONF_BASE_URL], entry.data[CONF_API_KEY])

    coordinator = BotpanelCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_envoyer(call: ServiceCall) -> None:
        """Action botpanel.envoyer : déclenche une notif (liste déroulante, slug ou id)."""
        notif_id = call.data.get("id")
        slug = call.data.get("slug")
        entity_id = call.data.get("notification")
        if entity_id and notif_id is None and not slug:
            notif_id = _notif_id_from_entity(hass, entity_id)
        await api.trigger(notif_id=notif_id, slug=slug)

    hass.services.async_register(DOMAIN, SERVICE_ENVOYER, _handle_envoyer, schema=SERVICE_SCHEMA)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge l'intégration."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_ENVOYER)
    return unloaded
