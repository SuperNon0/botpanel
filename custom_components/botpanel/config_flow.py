"""Écran de configuration (UI) du composant BotPanel : URL + clé API."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BotpanelApi, BotpanelApiError, BotpanelAuthError
from .const import CONF_API_KEY, CONF_BASE_URL, DOMAIN


class BotpanelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère l'ajout de l'intégration BotPanel depuis l'interface HA."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = BotpanelApi(session, user_input[CONF_BASE_URL], user_input[CONF_API_KEY])
            try:
                await api.ping()
            except BotpanelAuthError:
                errors["base"] = "invalid_auth"
            except BotpanelApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id("botpanel")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="BotPanel", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default="http://192.168.1.x:8080"): str,
                vol.Required(CONF_API_KEY): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
