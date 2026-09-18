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
from app.auth import auth_state, verify_session_token, COOKIE_NAME, cf_access_email, cf_config
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


def _blocked_response(request):
    """Acces direct refuse (mode Cloudflare uniquement) : 403.

    - Navigation web (GET HTML) -> page « Acces refuse » (bloque.html), statut 403.
    - Tout le reste (API, POST…) -> JSON 403. La page machine reste, elle, ouverte
      car filtree en amont par `_AUTH_PUBLIC_PREFIXES`.
    """
    accept = request.headers.get("accept", "")
    if request.method == "GET" and "text/html" in accept:
        # Import differe pour eviter un cycle a l'import du module.
        from app.api.routes.web import templates
        email = request.headers.get("cf-access-authenticated-user-email") or "—"
        return templates.TemplateResponse(
            "bloque.html",
            {"request": request, "email": email, "active_page": "login"},
            status_code=403,
        )
    return JSONResponse({"detail": "Acces refuse (Cloudflare uniquement)."}, status_code=403)


async def _auth_guard(request, call_next):
    """Controle d'acces a deux portes + mode « Cloudflare uniquement ».

    Portes d'entree acceptees :
      1. un badge Cloudflare valide (JWT verifie), OU
      2. une session mot de passe (LAN) — uniquement si l'entree locale est permise.

    Selon la config :
      - allow_local = True  : entree LAN autorisee (mot de passe si active, sinon ouvert).
      - allow_local = False : entree UNIQUEMENT via Cloudflare ; tout acces direct
        (sans badge valide) est refuse (403), meme en POST.

    Les routes machine (/api/notify, webhooks) restent TOUJOURS ouvertes
    (filtrees par `_AUTH_PUBLIC_PREFIXES`) : elles se protegent par cle API / LAN.
    Les pages web protegees sont redirigees vers /login ; les appels API -> 401.
    """
    if settings.is_configured:
        path = request.url.path
        if not any(path.startswith(p) for p in _AUTH_PUBLIC_PREFIXES):
            cfg = await cf_config()
            state = await auth_state()
            local_disabled = not cfg["allow_local"]
            # On ne filtre que s'il y a quelque chose a faire respecter :
            #   - un mot de passe est actif, OU
            #   - l'entree locale est desactivee (mode Cloudflare uniquement).
            if state["enabled"] or local_disabled:
                # Porte 1 : badge Cloudflare verifie ?
                cf_ok = False
                try:
                    if await cf_access_email(request):
                        cf_ok = True
                except Exception:  # noqa: BLE001
                    cf_ok = False

                if not cf_ok:
                    if local_disabled:
                        # Cloudflare uniquement : acces direct refuse (403).
                        return _blocked_response(request)
                    # Porte 2 : session mot de passe (LAN), si un mot de passe est actif.
                    authed = True
                    if state["enabled"]:
                        token = request.cookies.get(COOKIE_NAME)
                        authed = bool(
                            token and state["secret"]
                            and verify_session_token(token, state["secret"])
                        )
                    if not authed:
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
