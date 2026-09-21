"""Routes du site web (pages HTML servies via Jinja)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth import cf_config

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


# ----------------------------------------------------------------------
# PWA : manifest + service worker (servis a la racine pour un scope "/").
# ----------------------------------------------------------------------
_MANIFEST = {
    "name": "BotPanel",
    "short_name": "botpanel",
    "description": "Bot Discord x Home Assistant — panneau d'administration",
    "lang": "fr",
    "start_url": "/dashboard",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0e0f11",
    "theme_color": "#0e0f11",
    "icons": [
        {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

# Service worker : network-first, cache de repli hors-ligne. Ne met JAMAIS en
# cache les appels /api/ (donnees live / webhooks machines).
_SERVICE_WORKER = """\
const CACHE = 'botpanel-v1';
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) =>
    Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return; // jamais de cache pour l'API
  e.respondWith(
    fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(req))
  );
});
"""


@router.get("/manifest.webmanifest", include_in_schema=False)
async def pwa_manifest():
    return JSONResponse(_MANIFEST, media_type="application/manifest+json")


@router.get("/sw.js", include_in_schema=False)
async def pwa_service_worker():
    return Response(
        _SERVICE_WORKER,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@router.get("/setup", response_class=HTMLResponse)
async def page_setup(request: Request):
    return templates.TemplateResponse(
        "setup.html", {"request": request, "active_page": "setup"}
    )


@router.get("/login", response_class=HTMLResponse)
async def page_login(request: Request):
    # Mode « Cloudflare uniquement » : pas de login local -> page « Acces refuse ».
    cfg = await cf_config()
    if not cfg["allow_local"]:
        email = request.headers.get("cf-access-authenticated-user-email") or "—"
        return templates.TemplateResponse(
            "bloque.html",
            {"request": request, "email": email, "active_page": "login"},
            status_code=403,
        )
    return templates.TemplateResponse(
        "login.html", {"request": request, "active_page": "login"}
    )


@router.get("/login/forgot", response_class=HTMLResponse)
async def page_forgot(request: Request):
    return templates.TemplateResponse(
        "forgot.html", {"request": request, "active_page": "login"}
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "active_page": "dashboard"}
    )


@router.get("/notifications", response_class=HTMLResponse)
async def page_notifications(request: Request):
    return templates.TemplateResponse(
        "notifications/list.html", {"request": request, "active_page": "notifications"}
    )


@router.get("/notifications/new", response_class=HTMLResponse)
async def page_notification_new(request: Request):
    return templates.TemplateResponse(
        "notifications/edit.html",
        {"request": request, "active_page": "notifications", "notif_id": None},
    )


@router.get("/notifications/{notif_id}", response_class=HTMLResponse)
async def page_notification_edit(request: Request, notif_id: int):
    return templates.TemplateResponse(
        "notifications/edit.html",
        {"request": request, "active_page": "notifications", "notif_id": notif_id},
    )


@router.get("/commands", response_class=HTMLResponse)
async def page_commands(request: Request):
    return templates.TemplateResponse(
        "commands/list.html", {"request": request, "active_page": "commands"}
    )


@router.get("/commands/new", response_class=HTMLResponse)
async def page_command_new(request: Request):
    return templates.TemplateResponse(
        "commands/edit.html",
        {"request": request, "active_page": "commands", "cmd_id": None},
    )


@router.get("/commands/{cmd_id}", response_class=HTMLResponse)
async def page_command_edit(request: Request, cmd_id: int):
    return templates.TemplateResponse(
        "commands/edit.html",
        {"request": request, "active_page": "commands", "cmd_id": cmd_id},
    )


@router.get("/monitoring", response_class=HTMLResponse)
async def page_monitoring(request: Request):
    return templates.TemplateResponse(
        "monitoring/list.html", {"request": request, "active_page": "monitoring"}
    )


@router.get("/monitoring/new", response_class=HTMLResponse)
async def page_monitoring_new(request: Request):
    return templates.TemplateResponse(
        "monitoring/edit.html",
        {"request": request, "active_page": "monitoring", "block_id": None},
    )


@router.get("/monitoring/{block_id}", response_class=HTMLResponse)
async def page_monitoring_edit(request: Request, block_id: int):
    return templates.TemplateResponse(
        "monitoring/edit.html",
        {"request": request, "active_page": "monitoring", "block_id": block_id},
    )


@router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    return templates.TemplateResponse(
        "settings/index.html", {"request": request, "active_page": "settings"}
    )


@router.get("/historique", response_class=HTMLResponse)
async def page_history(request: Request):
    return templates.TemplateResponse(
        "history/index.html", {"request": request, "active_page": "historique"}
    )


@router.get("/aide", response_class=HTMLResponse)
async def page_help(request: Request):
    return templates.TemplateResponse(
        "help/index.html", {"request": request, "active_page": "aide"}
    )
