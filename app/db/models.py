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
    image_url: Optional[str] = None
    footer: Optional[str] = None
    show_timestamp: bool = False
    delete_button: bool = False
    snooze_button: bool = False
    snooze_minutes: int = 15
    # group_name : nom du fil (thread) ou du post (forum) cote Discord
    group_name: Optional[str] = Field(default=None, max_length=64)
    # list_group : rangement sur la liste du site (independant de Discord)
    list_group: Optional[str] = Field(default=None, max_length=64)
    thread_mode: Literal["none", "thread", "forum"] = "none"
    mention: Optional[str] = Field(default=None, max_length=128)
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
#  Boutons d'action HA generiques (commandes + monitoring)
# ==========================================================
class HaButton(BaseModel):
    """Bouton Discord qui appelle un service Home Assistant au clic.

    Meme forme que les boutons de notification, mais stocke en JSON
    (commandes : colonne `buttons_json`, monitoring : `config_json.buttons`).
    """

    label: str = Field(..., max_length=80)
    style: Literal["primary", "secondary", "success", "danger"] = "primary"
    emoji: Optional[str] = None
    ha_service: str = Field(..., description="Ex: light.toggle")
    ha_entity_id: Optional[str] = None
    ha_data_json: Optional[str] = None


# ==========================================================
#  Commandes slash
# ==========================================================
# "message" = pas d'action HA, la commande repond juste (ex: /temperature
# qui affiche {state:sensor.temp_salon}).
ActionType = Literal["service", "script", "scene", "notification", "message"]


class SlashCommandIn(BaseModel):
    name: str = Field(..., pattern=r"^[a-z0-9_-]{1,32}$")
    description: str = Field(..., max_length=100)
    action_type: ActionType
    ha_service: Optional[str] = None
    ha_entity_id: Optional[str] = None
    ha_data_json: Optional[str] = None
    notification_slug: Optional[str] = None
    # Reponse : texte avec placeholders HA ({state:...}, Jinja) resolus a l'envoi.
    response_message: str = Field("OK", max_length=4000)
    response_ephemeral: bool = True          # visible seulement par l'auteur
    response_embed: bool = False             # reponse en embed (titre/couleur/image)
    response_title: Optional[str] = Field(default=None, max_length=256)
    response_color: int = Field(0xE8C547, ge=0, le=0xFFFFFF)
    response_image_url: Optional[str] = None
    buttons: list[HaButton] = Field(default_factory=list, max_length=20)
    # list_group : rangement sur la liste du site
    list_group: Optional[str] = Field(default=None, max_length=64)
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
          "description": "Texte sous le titre ({state:...} / Jinja acceptes)",
          "thumbnail_url": "https://...",   # petite image (placeholders acceptes)
          "image_url": "https://...",       # grande image
          "show_timestamp": true,           # date de mise a jour dans le footer
          "refresh_button": true,           # bouton "Actualiser" sous le message
          "buttons": [ {label, style, emoji, ha_service, ha_entity_id, ha_data_json} ],
          "fields": [
            {
              "label": "Temperature",       # placeholders acceptes
              "icon": "\U0001f321️",
              "entity_id": "sensor.temp_salon",
              "attribute": null,           # ou "humidity" pour lire un attribut
              "suffix": "°C",              # vide = unite HA automatique
              "decimals": 1,               # arrondi optionnel des nombres
              "value_template": "",        # si rempli : remplace entity_id
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
    # list_group : rangement sur la liste du site
    list_group: Optional[str] = Field(default=None, max_length=64)


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


# ==========================================================
#  Threads Discord
# ==========================================================
class NotificationThread(BaseModel):
    id: int
    group_name: str
    channel_id: str
    thread_id: str
    created_at: str


# ==========================================================
#  Historique
# ==========================================================
class NotificationLog(BaseModel):
    id: int
    notification_id: Optional[int] = None
    notification_slug: Optional[str] = None
    channel_id: Optional[str] = None
    message_id: Optional[str] = None
    kind: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    button_label: Optional[str] = None
    detail: Optional[str] = None
    source: Optional[str] = None
    success: bool = True
    created_at: str
