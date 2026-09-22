"""Un bouton Home Assistant par notification BotPanel (appui = envoi)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import BotpanelEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    notifications = (coordinator.data or {}).get("notifications", [])
    async_add_entities(
        BotpanelNotifButton(coordinator, entry.entry_id, n) for n in notifications
    )


class BotpanelNotifButton(BotpanelEntity, ButtonEntity):
    """Bouton qui déclenche l'envoi d'une notification BotPanel."""

    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry_id: str, notif: dict) -> None:
        super().__init__(coordinator, entry_id)
        self._notif_id = notif["id"]
        self._slug = notif["slug"]
        self._attr_name = notif.get("title") or notif["slug"]
        self._attr_unique_id = f"{entry_id}_notif_{notif['id']}"

    async def async_press(self) -> None:
        await self.coordinator.api.trigger(notif_id=self._notif_id, slug=self._slug)
