"""Capteurs BotPanel : envois du jour / total, nb de notifs, dernière alerte."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import BotpanelEntity

# (clé dans state, nom, icône, state_class)
#  - sent_today / sent_total : compteurs -> TOTAL_INCREASING (gère les resets)
#  - notif_count : jauge instantanée -> MEASUREMENT
_STATS = [
    ("sent_today", "Envois du jour", "mdi:counter", SensorStateClass.TOTAL_INCREASING),
    ("sent_total", "Envois total", "mdi:sigma", SensorStateClass.TOTAL_INCREASING),
    ("notif_count", "Notifications configurées", "mdi:bell", SensorStateClass.MEASUREMENT),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        BotpanelStatSensor(coordinator, entry.entry_id, key, name, icon, state_class)
        for key, name, icon, state_class in _STATS
    ]
    entities.append(BotpanelLastAlertSensor(coordinator, entry.entry_id))
    async_add_entities(entities)


class BotpanelStatSensor(BotpanelEntity, SensorEntity):
    """Capteur numérique simple lu dans /state."""

    def __init__(self, coordinator, entry_id: str, key: str, name: str, icon: str, state_class) -> None:
        super().__init__(coordinator, entry_id)
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_state_class = state_class
        self._attr_unique_id = f"{entry_id}_{key}"

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("state", {}).get(self._key)


class BotpanelLastAlertSensor(BotpanelEntity, SensorEntity):
    """Horodatage de la dernière notification envoyée."""

    _attr_name = "Dernière alerte"
    _attr_icon = "mdi:history"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_last_alert"

    @property
    def native_value(self):
        last = (self.coordinator.data or {}).get("state", {}).get("last_alert")
        if not last or not last.get("created_at"):
            return None
        raw = str(last["created_at"]).replace("T", " ").strip()
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        # BotPanel stocke en UTC ; on rend l'horodatage conscient du fuseau.
        return dt.replace(tzinfo=timezone.utc)

    @property
    def extra_state_attributes(self):
        last = (self.coordinator.data or {}).get("state", {}).get("last_alert") or {}
        return {"slug": last.get("slug"), "source": last.get("source")}
