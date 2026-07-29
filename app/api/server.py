"""Application FastAPI : API REST + serveur du site web."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import (
    auth as auth_routes,
    backup as backup_routes,
    dashboard as dashboard_routes,
    discord as discord_routes,
    ha_hook,
    ha_proxy,
    logs,
    monitoring,
    notifications,
    setup as setup_routes,
    settings as settings_routes,
    slash_commands,
    system as system_routes,
    web,
)
from app.auth import auth_state, verify_session_token, COOKIE_NAME
from app.config import settings

logger = logging.getLogger(__name__)


# Chemins toujours accessibles, meme en mode configuration (sinon on ne pourrait
# pas afficher /setup, servir le CSS, ni verifier l'etat du service).
_SETUP_ALLOWED_PREFIXES = ("/setup", "/api/setup", "/static", "/health", "/api/system")

# Chemins toujours accessibles meme quand la protection par mot de passe est active :
# - la page de connexion et son API
# - les assets statiques et le health-check
# - IMPORTANT : /api/notify (et webhooks) pour ne jamais bloquer Home Assistant / Proxmox
_AUTH_PUBLIC_PREFIXES = (
    "/login", "/api/auth", "/static", "/health", "/favicon", "/api/notify",
)


async def _setup_guard(request, call_next):
    """En mode configuration, redirige les pages web vers l'assistant /setup.

    IMPORTANT : ne bloque JAMAIS les routes /api/... utilisees par des machines
    (Home Assistant, Proxmox). Seule la navigation web (GET HTML) est redirigee.
    """
    if not settings.is_configured:
        path = request.url.path
        if not any(path.startswith(p) for p in _SETUP_ALLOWED_PREFIXES):
            accept = request.headers.get("accept", "")
            if request.method == "GET" and "text/html" in accept:
                return RedirectResponse("/setup")
    return await call_next(request)


async def _auth_guard(request, call_next):
    """Si un mot de passe admin est defini, exige une session valide.

    Les routes machine (/api/notify, webhooks) restent toujours ouvertes.
    Les pages web sont redirigees vers /login ; les appels API renvoient 401.
    """
    if settings.is_configured:
        path = request.url.path
        if not any(path.startswith(p) for p in _AUTH_PUBLIC_PREFIXES):
            state = await auth_state()
            if state["enabled"]:
                token = request.cookies.get(COOKIE_NAME)
                user = verify_session_token(token, state["secret"]) if (token and state["secret"]) else None
                if user is None:
                    accept = request.headers.get("accept", "")
                    if request.method == "GET" and "text/html" in accept:
                        return RedirectResponse("/login")
                    return JSONResponse({"detail": "Non authentifie"}, status_code=401)
    return await call_next(request)


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

    # Middlewares (le dernier ajoute s'execute en premier) :
    # protection par mot de passe, puis redirection vers l'assistant de config.
    app.add_middleware(BaseHTTPMiddleware, dispatch=_auth_guard)
    app.add_middleware(BaseHTTPMiddleware, dispatch=_setup_guard)

    # --- API ---
    app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])
    app.include_router(setup_routes.router, prefix="/api/setup", tags=["setup"])
    app.include_router(backup_routes.router, prefix="/api/backup", tags=["backup"])
    app.include_router(dashboard_routes.router, prefix="/api/dashboard", tags=["dashboard"])
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
        if not settings.is_configured:
            return RedirectResponse("/setup")
        return RedirectResponse("/dashboard")

    @app.get("/health", include_in_schema=False)
    async def _health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
