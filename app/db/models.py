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
BlockType = Literal["temperature", "power"]


class MonitoringBlockIn(BaseModel):
    enabled: bool = False
    channel_id: Optional[str] = None
    interval_seconds: int = Field(300, ge=30)
    config_json: str = "{}"


class MonitoringBlock(MonitoringBlockIn):
    id: int
    block_type: BlockType
    message_id: Optional[str] = None
