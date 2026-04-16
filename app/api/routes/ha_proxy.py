"""Routes proxy vers Home Assistant pour l'autocompletion du site."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.ha import ha_client
from app.ha.client import HomeAssistantError

router = APIRouter()


@router.get("/entities")
async def list_entities(domain: Optional[str] = None) -> list[dict[str, str]]:
    """Liste les entites HA disponibles (filtrable par domaine)."""
    try:
        return await ha_client.list_entity_ids(domain_filter=domain)
    except HomeAssistantError as exc:
        raise HTTPException(502, f"HA inaccessible : {exc}") from exc


@router.get("/services")
async def list_services() -> list[dict[str, str]]:
    """Liste plate des services HA (pour l'autocompletion)."""
    try:
        return await ha_client.list_services_flat()
    except HomeAssistantError as exc:
        raise HTTPException(502, f"HA inaccessible : {exc}") from exc


@router.get("/ping")
async def ping() -> dict[str, bool]:
    return {"ok": await ha_client.ping()}
