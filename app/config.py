"""Chargement de la configuration depuis le fichier .env.

Les champs essentiels ne sont plus obligatoires au demarrage : si le .env
est incomplet, l'application demarre en "mode configuration" et affiche
l'assistant de configuration (page /setup) au lieu de planter.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Configuration globale de l'application (lue depuis .env)."""

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Discord ---
    # Valeurs vides par defaut : permet le demarrage en mode configuration.
    discord_token: str = Field("", description="Token du bot Discord")
    discord_guild_id: int = Field(0, description="ID du serveur Discord")
    discord_default_channel_id: int = Field(
        0, description="Channel par defaut pour les notifications"
    )
    discord_monitoring_channel_id: int = Field(
        0, description="Channel pour les messages de monitoring"
    )

    # --- Home Assistant ---
    ha_base_url: str = Field("", description="URL locale de HA, ex http://IP:8123")
    ha_token: str = Field("", description="Token longue duree HA")

    # --- API / Web ---
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    site_base_url: str = "http://localhost:8080"

    # --- Stockage ---
    database_path: Path = PROJECT_ROOT / "data" / "botpanel.db"

    # --- Logs ---
    log_level: str = "INFO"

    @property
    def ha_api_url(self) -> str:
        """URL de base de l'API REST de Home Assistant."""
        return f"{self.ha_base_url.rstrip('/')}/api"

    @property
    def is_configured(self) -> bool:
        """True si les informations essentielles sont presentes.

        Sert a decider si l'app tourne normalement (bot + site) ou si elle
        affiche l'assistant de configuration au premier lancement.
        """
        return bool(
            self.discord_token
            and self.discord_guild_id
            and self.discord_default_channel_id
            and self.ha_base_url
            and self.ha_token
        )


settings = Settings()
