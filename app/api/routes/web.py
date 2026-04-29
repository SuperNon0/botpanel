"""Routes du site web (pages HTML servies via Jinja)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


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
