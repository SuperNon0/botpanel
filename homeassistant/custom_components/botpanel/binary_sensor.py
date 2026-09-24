"""Capteur binaire : le bot Discord de BotPanel est-il en ligne ?"""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import BotpanelEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BotpanelBotOnline(coordinator, entry.entry_id)])


class BotpanelBotOnline(BotpanelEntity, BinarySensorEntity):
    """Indique si le bot Discord est connecté."""

    _attr_name = "Bot en ligne"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:robot"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_bot_online"

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("state", {}).get("bot_online"))
