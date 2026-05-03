"""Application FastAPI : API REST + serveur du site web."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    discord as discord_routes,
    ha_hook,
    ha_proxy,
    logs,
    monitoring,
    notifications,
    settings as settings_routes,
    slash_commands,
    system as system_routes,
    web,
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Instancie l'application FastAPI."""
    app = FastAPI(
        title="BotPanel",
        description="Bot Discord x Home Assistant — pilote depuis botpanel.super-nono.cc",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    # --- API ---
    app.include_router(ha_hook.router, prefix="/api", tags=["ha-hook"])
    app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
    app.include_router(slash_commands.router, prefix="/api/commands", tags=["commands"])
    app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])
    app.include_router(ha_proxy.router, prefix="/api/ha", tags=["ha"])
    app.include_router(settings_routes.router, prefix="/api/settings", tags=["settings"])
    app.include_router(discord_routes.router, prefix="/api/discord", tags=["discord"])
    app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
    app.include_router(system_routes.router, prefix="/api/system", tags=["system"])

    # --- Site web (Jinja templates) ---
    app.include_router(web.router, tags=["web"])

    # --- Assets statiques ---
    static_dir = Path(__file__).resolve().parent.parent / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def _root() -> RedirectResponse:
        return RedirectResponse("/notifications")

    @app.get("/health", include_in_schema=False)
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
