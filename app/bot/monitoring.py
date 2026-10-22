"""Taches periodiques de monitoring (multi-blocs).

Chaque bloc actif maintient un message Discord epingle qui est EDITE
(jamais supprime/recree) a chaque cycle. L'ID du message est persiste
dans la table monitoring_blocks pour survivre aux redemarrages.

Pour activer/desactiver/modifier a chaud depuis l'API :
  - update du bloc en DB
  - appel de `refresh_block_task(bot, block_id)`
  - ou `stop_block_task(block_id)` lors d'une suppression

Structure de `config_json` : voir `MonitoringBlockIn` (app/db/models.py).
Les textes (titre, description, footer, libelles, valeurs libres, URLs
d'image) acceptent les placeholders HA {state:...}/{attr:...}/{unit:...} et
le Jinja HA, resolus a chaque cycle avec les VRAIES valeurs.

Boutons sous le message (optionnels) : actions HA du bloc + « Actualiser » ;
apres un clic, le message est re-rendu immediatement (`refresh_block_now`).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from typing import Any, Optional

import discord

from app.bot.ha_actions import build_ha_buttons_view
from app.config import settings
from app.db.models import HaButton, MonitoringBlock
from app.db.repositories import LogRepository, MonitoringRepository
from app.ha import ha_client
from app.ha.client import HomeAssistantError

logger = logging.getLogger(__name__)


# block_id -> asyncio.Task
_tasks: dict[int, asyncio.Task] = {}


# -------------------------------------------------------------------
# Lecture de la config d'un bloc
# -------------------------------------------------------------------
def block_config(block: MonitoringBlock) -> dict[str, Any]:
    try:
        cfg = json.loads(block.config_json or "{}")
    except json.JSONDecodeError:
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def block_buttons(block: MonitoringBlock) -> list[HaButton]:
    """Boutons d'action HA du bloc (les entrees invalides sont ignorees)."""
    out: list[HaButton] = []
    for item in block_config(block).get("buttons") or []:
        try:
            if item.get("label") and item.get("ha_service"):
                out.append(HaButton(**item))
        except Exception:  # noqa: BLE001
            logger.warning("Bouton monitoring invalide ignore : %r", item)
    return out


def _is_url(value: str | None) -> bool:
    return bool(value) and str(value).strip().lower().startswith(("http://", "https://"))


# -------------------------------------------------------------------
# Resolution des valeurs
# -------------------------------------------------------------------
async def _tpl(text: str | None) -> str:
    """Resout {state:...}/{attr:...}/{unit:...}/Jinja HA dans un texte."""
    from app.bot.notifications import _resolve_template  # import tardif (cycle bot)

    if not text:
        return ""
    try:
        return await _resolve_template(text, None, resolve_vars=False)
    except Exception as exc:  # noqa: BLE001 — un champ ne doit jamais casser le bloc
        logger.warning("Resolution monitoring echouee (%r) : %s", text, exc)
        return text


def _format_number(value: Any, decimals: Any) -> Any:
    """Arrondit une valeur numerique si `decimals` est renseigne (sinon inchange)."""
    if decimals in (None, ""):
        return value
    try:
        return f"{float(value):.{max(0, min(6, int(decimals)))}f}"
    except (TypeError, ValueError):
        return value


async def _resolve_field_value(field: dict[str, Any]) -> str:
    """Resout la valeur a afficher pour un field d'un bloc monitoring.

    Deux modes :
      - `value_template` rempli : texte libre avec placeholders HA / Jinja
        (ex. "{state:sensor.temp|--} °C / {state:sensor.hum}%") ;
      - sinon `entity_id` (+ `attribute`) : la valeur de l'entite, avec le
        suffixe choisi ou, a defaut, l'unite HA de l'entite.
    """
    template = (field.get("value_template") or "").strip()
    entity_id = (field.get("entity_id") or "").strip()
    # Un placeholder colle dans « entite » est traite comme un template.
    if not template and "{" in entity_id:
        template, entity_id = entity_id, ""
    if template:
        return await _tpl(template) or "\u200b"

    if not entity_id:
        return "_entite manquante_"

    try:
        state = await ha_client.get_state(entity_id)
    except HomeAssistantError:
        state = None
    if state is None:
        return "_indisponible_"

    attrs = state.get("attributes", {}) or {}
    attribute = (field.get("attribute") or "").strip()
    if attribute:
        value = attrs.get(attribute)
        if value is None:
            return "_attribut absent_"
    else:
        value = state.get("state", "?")
        if value in ("unavailable", "unknown"):
            return "_indisponible_"

    value = _format_number(value, field.get("decimals"))
    suffix = field.get("suffix")
    if not suffix and not attribute:
        suffix = attrs.get("unit_of_measurement") or ""
    text = f"**{value}**"
    if suffix:
        text = f"{text} {suffix}"
    return text


async def render_block(block: MonitoringBlock) -> dict[str, Any]:
    """Calcule le contenu affiche d'un bloc (valeurs HA reelles incluses).

    Sert a la fois a l'embed Discord et a l'apercu de l'editeur.
    """
    cfg = block_config(block)

    title = await _tpl(block.name) or "Monitoring"
    icon = (block.icon or "").strip()
    thumbnail = (await _tpl(cfg.get("thumbnail_url"))).strip()
    if icon and _is_url(icon):
        thumbnail = thumbnail or icon      # une icone URL devient la miniature
    elif icon:
        title = f"{icon}  {title}"

    image = (await _tpl(cfg.get("image_url"))).strip()

    fields: list[dict[str, Any]] = []
    for field in (cfg.get("fields") or [])[:25]:
        label = await _tpl(field.get("label")) or field.get("entity_id") or "Champ"
        if field.get("icon"):
            label = f"{field['icon']} {label}"
        fields.append({
            "name": label[:256],
            "value": (await _resolve_field_value(field))[:1024],
            "inline": bool(field.get("inline", True)),
        })

    return {
        "title": title[:256],
        "description": (await _tpl(cfg.get("description")))[:4096],
        "fields": fields,
        "footer": (await _tpl(block.footer) or "Mise a jour")[:2048],
        "show_timestamp": cfg.get("show_timestamp", True) is not False,
        "thumbnail_url": thumbnail if _is_url(thumbnail) else "",
        "image_url": image if _is_url(image) else "",
        "buttons": [b.model_dump() for b in block_buttons(block)],
        "refresh_button": bool(cfg.get("refresh_button")),
    }


async def _build_embed(block: MonitoringBlock) -> discord.Embed:
    data = await render_block(block)
    embed = discord.Embed(
        title=data["title"],
        description=data["description"] or None,
        color=block.color,
        timestamp=dt.datetime.now(dt.timezone.utc) if data["show_timestamp"] else None,
    )
    if not data["fields"] and not data["description"]:
        embed.description = "_Aucun champ configure._"
    for f in data["fields"]:
        embed.add_field(name=f["name"], value=f["value"] or "\u200b", inline=f["inline"])
    if data["thumbnail_url"]:
        embed.set_thumbnail(url=data["thumbnail_url"])
    if data["image_url"]:
        embed.set_image(url=data["image_url"])
    embed.set_footer(text=data["footer"])
    return embed


def _build_view(block: MonitoringBlock) -> discord.ui.View | None:
    """Boutons sous le message : actions HA + « Actualiser » optionnel."""
    from app.bot.views import cid_monitoring_button, cid_monitoring_refresh

    extra = []
    if block_config(block).get("refresh_button"):
        extra.append(discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Actualiser",
            emoji="\U0001f504",
            custom_id=cid_monitoring_refresh(block.id),
        ))
    return build_ha_buttons_view(
        block_buttons(block),
        lambda idx: cid_monitoring_button(block.id, idx),
        extra,
    )


# -------------------------------------------------------------------
# Resolution du message a editer (creation si absent)
# -------------------------------------------------------------------
async def _ensure_message(
    bot_: discord.Client, block: MonitoringBlock
) -> Optional[discord.Message]:
    channel_id = block.channel_id or str(settings.discord_monitoring_channel_id)
    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        logger.error("channel_id invalide bloc=%s : %r", block.id, channel_id)
        return None

    channel = bot_.get_channel(cid)
    if channel is None:
        try:
            channel = await bot_.fetch_channel(cid)
        except discord.HTTPException as exc:
            logger.error("Impossible de fetch le channel %s : %s", cid, exc)
            return None

    repo = MonitoringRepository()

    # On tente de recuperer le message existant
    if block.message_id:
        try:
            return await channel.fetch_message(int(block.message_id))  # type: ignore[union-attr]
        except (discord.NotFound, discord.HTTPException):
            logger.info("Message monitoring introuvable pour bloc %s, recreation.", block.id)

    # Creation d'un nouveau message
    embed = await _build_embed(block)
    view = _build_view(block)
    try:
        if view is not None:
            message = await channel.send(embed=embed, view=view)  # type: ignore[union-attr]
        else:
            message = await channel.send(embed=embed)  # type: ignore[union-attr]
    except discord.HTTPException as exc:
        logger.error("Echec envoi message monitoring %s : %s", block.id, exc)
        return None

    try:
        await message.pin(reason="BotPanel monitoring")
    except discord.HTTPException:
        logger.warning("Impossible d'epingler le message (permission manquante ?)")

    await repo.set_message_id(block.id, str(message.id))
    return message


async def _update_block_message(
    bot_: discord.Client, block: MonitoringBlock
) -> tuple[Optional[discord.Message], bool, Optional[str]]:
    """Re-rend le bloc et edite son message. Renvoie (message, ok, detail)."""
    message = await _ensure_message(bot_, block)
    if message is None:
        return None, False, "Channel/message introuvable"
    try:
        embed = await _build_embed(block)
        # view=None retire d'eventuels anciens boutons supprimes dans l'editeur.
        await message.edit(embed=embed, view=_build_view(block))
        return message, True, None
    except discord.HTTPException as exc:
        logger.error("Edit du message monitoring %s echoue : %s", block.id, exc)
        return message, False, f"Edit Discord : {exc}"[:300]
    except HomeAssistantError as exc:
        logger.warning("HA indisponible pour bloc %s : %s", block.id, exc)
        return message, False, f"HA indisponible : {exc}"[:300]


async def refresh_block_now(bot_: discord.Client, block_id: int) -> bool:
    """Met a jour tout de suite le message d'un bloc actif (bouton / panel)."""
    block = await MonitoringRepository().get_by_id(block_id)
    if block is None or not block.enabled:
        return False
    _, ok, _ = await _update_block_message(bot_, block)
    return ok


# -------------------------------------------------------------------
# Boucle d'un bloc
# -------------------------------------------------------------------
async def _block_loop(bot_: discord.Client, block_id: int) -> None:
    repo = MonitoringRepository()
    log_repo = LogRepository()
    logger.info("Demarrage task monitoring bloc=%s", block_id)
    while True:
        block = await repo.get_by_id(block_id)
        if block is None or not block.enabled:
            logger.info("Arret task monitoring bloc=%s (desactive ou supprime).", block_id)
            return

        message, ok, detail = await _update_block_message(bot_, block)
        await log_repo.add(
            kind="monitoring",
            notification_slug=block.name,
            channel_id=block.channel_id,
            message_id=str(message.id) if message else None,
            detail=detail,
            success=ok,
        )

        await asyncio.sleep(max(30, block.interval_seconds))


# -------------------------------------------------------------------
# API du module (appele depuis client.py et les routes API)
# -------------------------------------------------------------------
async def stop_block_task(block_id: int) -> None:
    """Stoppe la task d'un bloc (avant suppression ou desactivation)."""
    existing = _tasks.pop(block_id, None)
    if existing is not None and not existing.done():
        existing.cancel()
        try:
            await existing
        except (asyncio.CancelledError, Exception):
            pass


async def refresh_block_task(bot_: discord.Client, block_id: int) -> None:
    """Redemarre la task d'un bloc (apres modif via l'API)."""
    await stop_block_task(block_id)

    repo = MonitoringRepository()
    block = await repo.get_by_id(block_id)
    if block is None or not block.enabled:
        return

    task = asyncio.create_task(_block_loop(bot_, block_id), name=f"monitor:{block_id}")
    _tasks[block_id] = task


async def start_monitoring_tasks(bot_: discord.Client) -> None:
    """Demarre les taches pour tous les blocs actives (appele dans setup_hook)."""
    repo = MonitoringRepository()
    blocks = await repo.list_all()
    for block in blocks:
        if block.enabled:
            await refresh_block_task(bot_, block.id)
    logger.info("%d tasks de monitoring actives", sum(1 for b in blocks if b.enabled))
