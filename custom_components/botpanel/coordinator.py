"""Coordinateur : interroge BotPanel périodiquement (notifications + état)."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BotpanelApi, BotpanelApiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class BotpanelCoordinator(DataUpdateCoordinator):
    """Récupère la liste des notifications et l'état exposé par BotPanel."""

    def __init__(self, hass: HomeAssistant, api: BotpanelApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            notifications = await self.api.notifications()
            state = await self.api.state()
        except BotpanelApiError as err:
            raise UpdateFailed(f"Erreur BotPanel : {err}") from err
        return {"notifications": notifications, "state": state}
