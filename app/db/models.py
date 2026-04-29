"""Schemas Pydantic representant les entites stockees en base."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ==========================================================
#  Notifications
# ==========================================================
class NotificationButton(BaseModel):
    id: Optional[int] = None
    position: int = 0
    label: str = Field(..., max_length=80)
    style: Literal["primary", "secondary", "success", "danger"] = "primary"
    emoji: Optional[str] = None
    ha_service: str = Field(..., description="Ex: light.turn_on")
    ha_entity_id: Optional[str] = None
    ha_data_json: Optional[str] = None


class NotificationField(BaseModel):
    """Champ d'embed (apparait en grille dans Discord).

    `value_template` peut contenir des placeholders qui seront resolus
    au moment de l'envoi via les etats Home Assistant :
        {state:sensor.xxx}              -> etat brut
        {state:sensor.xxx|--}           -> avec fallback si indisponible
        {attr:sensor.xxx:friendly_name} -> attribut precis
        {unit:sensor.xxx}               -> unit_of_measurement
    """

    id: Optional[int] = None
    position: int = 0
    name: str = Field(..., max_length=256)
    value_template: str = Field(..., max_length=1024)
    inline: bool = True


class NotificationIn(BaseModel):
    """Payload de creation/modification d'une notification."""

    slug: str = Field(..., pattern=r"^[a-z0-9_]+$", max_length=64)
    channel_id: str
    title: str = Field(..., max_length=256)
    message: str = Field(..., max_length=4000)
    color: int = 0xFFFF00
    icon_url: Optional[str] = None
    footer: Optional[str] = None
    show_timestamp: bool = False
    delete_button: bool = False
    snooze_button: bool = False
    snooze_minutes: int = 15
    buttons: list[NotificationButton] = Field(default_factory=list)
    fields: list[NotificationField] = Field(default_factory=list)

    @field_validator("snooze_minutes")
    @classmethod
    def _snooze_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("snooze_minutes doit etre >= 1")
        return v


class Notification(NotificationIn):
    id: int


# ==========================================================
#  Commandes slash
# ==========================================================
ActionType = Literal["service", "script", "scene", "notification"]


class SlashCommandIn(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9_-]{1,32}$")
    description: str = Field(..., max_length=100)
    action_type: ActionType
    ha_service: Optional[str] = None
    ha_entity_id: Optional[str] = None
    ha_data_json: Optional[str] = None
    notification_slug: Optional[str] = None
    response_message: str = "OK"
    enabled: bool = True


class SlashCommand(SlashCommandIn):
    id: int


# ==========================================================
#  Monitoring
# ==========================================================
class MonitoringBlockIn(BaseModel):
    """Payload de creation/modification d'un bloc de monitoring.

    `config_json` est un JSON serialise. Structure libre, mais le bot lit :
        {
          "fields": [
            {
              "label": "Temperature",
              "icon": "🌡️",
              "entity_id": "sensor.temp_salon",
              "attribute": null,           # ou "humidity" pour lire un attribut
              "suffix": "°C",
              "inline": true
            }
          ]
        }
    """

    name: str = Field("Bloc", max_length=128)
    icon: Optional[str] = None
    color: int = 0x49A0DF  # bleu par defaut
    enabled: bool = False
    channel_id: Optional[str] = None
    interval_seconds: int = Field(300, ge=30)
    footer: Optional[str] = None
    config_json: str = "{}"


class MonitoringBlock(MonitoringBlockIn):
    id: int
    message_id: Optional[str] = None


# ==========================================================
#  Settings (presets globaux)
# ==========================================================
class ColorPreset(BaseModel):
    name: str = Field(..., max_length=64)
    color: int = Field(..., ge=0, le=0xFFFFFF)


class ChannelPreset(BaseModel):
    name: str = Field(..., max_length=64)
    channel_id: str = Field(..., max_length=32)
