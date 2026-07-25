"""Assistant de configuration (premier lancement).

Au premier demarrage, si le .env est incomplet, l'application tourne en
"mode configuration". La page /setup permet de saisir toutes les informations
(token Discord, IDs de channels, URL + token HA...) qui sont ensuite ecrites
dans le fichier .env, puis le service redemarre pour tout prendre en compte.

Aucune manipulation de fichier en SSH n'est necessaire.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import ENV_PATH, settings

logger = logging.getLogger(__name__)
router = APIRouter()


class SetupPayload(BaseModel):
    """Valeurs saisies dans l'assistant de configuration."""

    discord_token: str = Field(..., min_length=10)
    discord_guild_id: int = Field(..., gt=0)
    discord_default_channel_id: int = Field(..., gt=0)
    discord_monitoring_channel_id: int = Field(..., gt=0)
    ha_base_url: str = Field(..., min_length=5)
    ha_token: str = Field(..., min_length=10)
    # Optionnels (valeurs par defaut si non fournis)
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    site_base_url: str = ""
    log_level: str = "INFO"


@router.get("/status")
async def setup_status() -> dict[str, bool]:
    """Indique si BotPanel est deja configure."""
    return {"configured": settings.is_configured}


def _env_line(key: str, value: object) -> str:
    """Ligne KEY=value pour le .env (compatible systemd EnvironmentFile).

    Les valeurs ne sont pas entourees de guillemets : les tokens Discord/HA et
    les URLs ne contiennent ni espace ni saut de ligne.
    """
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return f"{key}={text}"


def _build_env(payload: SetupPayload) -> str:
    site = payload.site_base_url.strip() or f"http://localhost:{payload.api_port}"
    lines = [
        "# =========================================",
        "# BotPanel — genere par l'assistant de configuration",
        "# =========================================",
        "",
        "# --- Discord ---",
        _env_line("DISCORD_TOKEN", payload.discord_token),
        _env_line("DISCORD_GUILD_ID", payload.discord_guild_id),
        _env_line("DISCORD_DEFAULT_CHANNEL_ID", payload.discord_default_channel_id),
        _env_line("DISCORD_MONITORING_CHANNEL_ID", payload.discord_monitoring_channel_id),
        "",
        "# --- Home Assistant ---",
        _env_line("HA_BASE_URL", payload.ha_base_url),
        _env_line("HA_TOKEN", payload.ha_token),
        "",
        "# --- API / Site web ---",
        _env_line("API_HOST", payload.api_host),
        _env_line("API_PORT", payload.api_port),
        _env_line("SITE_BASE_URL", site),
        "",
        "# --- Logs ---",
        _env_line("LOG_LEVEL", payload.log_level or "INFO"),
        "",
    ]
    return "\n".join(lines)


@router.post("")
async def save_setup(payload: SetupPayload) -> dict[str, object]:
    """Ecrit le .env puis redemarre le service.

    Autorise uniquement tant que BotPanel n'est pas configure, pour eviter
    qu'on reecrive la configuration une fois le service en production.
    """
    if settings.is_configured:
        raise HTTPException(
            status_code=409,
            detail="BotPanel est deja configure. Modifie le fichier .env pour changer la config.",
        )

    try:
        ENV_PATH.write_text(_build_env(payload), encoding="utf-8")
    except OSError as exc:
        logger.error("Impossible d'ecrire %s : %s", ENV_PATH, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Impossible d'ecrire le fichier .env ({exc}).",
        )

    logger.info("Configuration enregistree dans %s — redemarrage...", ENV_PATH)

    async def _restart_after_response() -> None:
        await asyncio.sleep(0.6)
        os._exit(1)  # systemd (Restart=on-failure) relance le service

    asyncio.create_task(_restart_after_response())
    return {"status": "saved", "restarting": True}
