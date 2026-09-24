"""Un bouton Home Assistant par notification BotPanel (appui = envoi)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import BotpanelEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _sync_buttons() -> None:
        """Ajoute les boutons des nouvelles notifications au fil des rafraîchissements."""
        new_entities = []
        for notif in (coordinator.data or {}).get("notifications", []):
            uid = f"{entry.entry_id}_notif_{notif['id']}"
            if uid not in known:
                known.add(uid)
                new_entities.append(BotpanelNotifButton(coordinator, entry.entry_id, notif))
        if new_entities:
            async_add_entities(new_entities)

    _sync_buttons()
    # Nouvelles notifications créées dans BotPanel -> boutons ajoutés automatiquement.
    entry.async_on_unload(coordinator.async_add_listener(_sync_buttons))


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
