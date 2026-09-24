"""Base commune : rattache toutes les entités à l'appareil « BotPanel »."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BotpanelCoordinator


class BotpanelEntity(CoordinatorEntity[BotpanelCoordinator]):
    """Entité de base rattachée à l'appareil BotPanel."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BotpanelCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="BotPanel",
            manufacturer="BotPanel",
            model="Bot Discord × Home Assistant",
        )
