"""CRUD des templates de notifications Proxmox."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.db.models import ProxmoxNotification, ProxmoxNotificationIn
from app.db.repositories import ProxmoxNotificationRepository

router = APIRouter()
repo = ProxmoxNotificationRepository()


@router.get("", response_model=list[ProxmoxNotification])
async def list_proxmox_notifications() -> list[ProxmoxNotification]:
    return await repo.list_all()


@router.post("", response_model=ProxmoxNotification, status_code=201)
async def create_proxmox_notification(payload: ProxmoxNotificationIn) -> ProxmoxNotification:
    return await repo.create(payload)


@router.get("/{notif_id}", response_model=ProxmoxNotification)
async def get_proxmox_notification(notif_id: int) -> ProxmoxNotification:
    n = await repo.get_by_id(notif_id)
    if n is None:
        raise HTTPException(404, "Notification Proxmox introuvable")
    return n


@router.put("/{notif_id}", response_model=ProxmoxNotification)
async def update_proxmox_notification(
    notif_id: int, payload: ProxmoxNotificationIn
) -> ProxmoxNotification:
    n = await repo.update(notif_id, payload)
    if n is None:
        raise HTTPException(404, "Notification Proxmox introuvable")
    return n


@router.delete("/{notif_id}", status_code=204, response_class=Response)
async def delete_proxmox_notification(notif_id: int):
    ok = await repo.delete(notif_id)
    if not ok:
        raise HTTPException(404, "Notification Proxmox introuvable")
    return Response(status_code=204)


@router.post("/{notif_id}/test", status_code=202)
async def test_proxmox_notification(notif_id: int) -> dict[str, str]:
    """Envoie la notification avec des donnees d'exemple."""
    from app.api.routes.proxmox_hook import send_proxmox_notification

    n = await repo.get_by_id(notif_id)
    if n is None:
        raise HTTPException(404, "Notification Proxmox introuvable")

    sample = {
        "severity": n.event_type if n.event_type != "any" else "info",
        "title": "Backup vzdump — test",
        "body": "Backup de la VM 100 (debian-web) termine en 2m 34s.",
        "vmid": "100",
        "hostname": "pve-node",
        "type": "lxc",
        "storage": "local-zfs",
        "duration": "154",
        "size": "2147483648",
    }
    count = await send_proxmox_notification(n, sample)
    return {"status": "sent", "messages": str(count)}
