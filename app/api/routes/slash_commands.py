"""CRUD des commandes slash Discord."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.db.models import SlashCommand, SlashCommandIn
from app.db.repositories import SlashCommandRepository
from app.db.repositories.slash_commands import MAX_SLASH_COMMANDS

router = APIRouter()
repo = SlashCommandRepository()


async def _resync_discord() -> None:
    """Appelle la sync Discord apres toute modif."""
    from app.bot.client import bot
    from app.bot.slash_sync import sync_slash_commands
    if bot.is_ready():
        await sync_slash_commands(bot)


async def _check_name(payload: SlashCommandIn, cmd_id: int | None = None) -> None:
    """Refuse un nom reserve (/ha, /clear) ou deja pris par une autre commande."""
    from app.bot.slash_sync import RESERVED_NAMES

    if payload.name in RESERVED_NAMES:
        raise HTTPException(400, f"/{payload.name} est une commande fixe de BotPanel (nom reserve)")
    other = await repo.get_by_name(payload.name)
    if other is not None and other.id != cmd_id:
        raise HTTPException(409, f"/{payload.name} existe deja")


@router.get("", response_model=list[SlashCommand])
async def list_commands() -> list[SlashCommand]:
    return await repo.list_all()


@router.get("/quota")
async def get_quota() -> dict[str, int]:
    count = await repo.count()
    return {"used": count, "max": MAX_SLASH_COMMANDS, "remaining": MAX_SLASH_COMMANDS - count}


@router.get("/{cmd_id}", response_model=SlashCommand)
async def get_command(cmd_id: int) -> SlashCommand:
    cmd = await repo.get_by_id(cmd_id)
    if cmd is None:
        raise HTTPException(404, "Commande introuvable")
    return cmd


@router.post("", response_model=SlashCommand, status_code=201)
async def create_command(payload: SlashCommandIn) -> SlashCommand:
    count = await repo.count()
    if count >= MAX_SLASH_COMMANDS:
        raise HTTPException(
            400, f"Limite Discord atteinte ({MAX_SLASH_COMMANDS} commandes max)"
        )
    await _check_name(payload)
    cmd = await repo.create(payload)
    await _resync_discord()
    return cmd


@router.put("/{cmd_id}", response_model=SlashCommand)
async def update_command(cmd_id: int, payload: SlashCommandIn) -> SlashCommand:
    await _check_name(payload, cmd_id)
    cmd = await repo.update(cmd_id, payload)
    if cmd is None:
        raise HTTPException(404, "Commande introuvable")
    await _resync_discord()
    return cmd


@router.delete("/{cmd_id}", status_code=204, response_class=Response)
async def delete_command(cmd_id: int):
    ok = await repo.delete(cmd_id)
    if not ok:
        raise HTTPException(404, "Commande introuvable")
    await _resync_discord()
    return Response(status_code=204)


@router.post("/{cmd_id}/duplicate", response_model=SlashCommand, status_code=201)
async def duplicate_command(cmd_id: int) -> SlashCommand:
    """Duplique une commande (nom `<nom>-copie`, `-copie2`…), creee desactivee."""
    src = await repo.get_by_id(cmd_id)
    if src is None:
        raise HTTPException(404, "Commande introuvable")
    if await repo.count() >= MAX_SLASH_COMMANDS:
        raise HTTPException(400, f"Limite Discord atteinte ({MAX_SLASH_COMMANDS} commandes max)")

    n = 1
    while True:
        suffix = "-copie" if n == 1 else f"-copie{n}"
        name = src.name[: 32 - len(suffix)] + suffix
        if await repo.get_by_name(name) is None:
            break
        n += 1

    payload = SlashCommandIn(**{**src.model_dump(exclude={"id"}), "name": name, "enabled": False})
    return await repo.create(payload)


@router.post("/preview")
async def preview_command(payload: SlashCommandIn) -> dict:
    """Reponse d'un brouillon avec les VRAIES valeurs HA (rien n'est execute)."""
    from app.bot.slash_sync import render_command_response
    from app.ha import ha_client

    try:
        ha_ok = bool(await ha_client.ping())
    except Exception:  # noqa: BLE001
        ha_ok = False
    data = await render_command_response(SlashCommand(id=0, **payload.model_dump()))
    return {"ha_ok": ha_ok, **data}


@router.post("/{cmd_id}/test")
async def test_command(cmd_id: int) -> dict:
    """Execute l'action de la commande depuis le site (comme si on la tapait).

    Renvoie la reponse qui aurait ete affichee sur Discord.
    """
    from app.bot.slash_sync import _execute_action, render_command_response
    from app.ha.client import HomeAssistantError

    cmd = await repo.get_by_id(cmd_id)
    if cmd is None:
        raise HTTPException(404, "Commande introuvable")
    try:
        await _execute_action(cmd)
    except HomeAssistantError as exc:
        raise HTTPException(502, f"Action echouee : {exc}")
    return {"status": "ok", **(await render_command_response(cmd))}
