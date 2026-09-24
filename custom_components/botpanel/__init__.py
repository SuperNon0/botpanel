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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BotpanelApi
from .const import CONF_API_KEY, CONF_BASE_URL, DOMAIN, PLATFORMS, SERVICE_ENVOYER
from .coordinator import BotpanelCoordinator

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("slug"): cv.string,
        vol.Optional("id"): vol.Coerce(int),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place l'intégration à partir d'une entrée de configuration."""
    session = async_get_clientsession(hass)
    api = BotpanelApi(session, entry.data[CONF_BASE_URL], entry.data[CONF_API_KEY])

    coordinator = BotpanelCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_envoyer(call: ServiceCall) -> None:
        """Action botpanel.envoyer : déclenche une notif par slug ou id."""
        await api.trigger(notif_id=call.data.get("id"), slug=call.data.get("slug"))

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
