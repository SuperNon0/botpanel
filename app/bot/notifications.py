"""Construction et envoi des notifications Discord."""

from __future__ import annotations

import datetime as dt
import logging
import re

import discord

from app.bot.client import bot
from app.bot.views import build_notification_view
from app.config import settings
from app.db.models import Notification
from app.db.repositories import LogRepository, NotificationRepository
from app.ha import ha_client

logger = logging.getLogger(__name__)


STYLE_TO_COLOR: dict[str, int] = {
    "yellow": 0xFFD93D,
    "green": 0x4ADE80,
    "purple": 0x8B5CF6,
    "orange": 0xF59E0B,
    "red": 0xEF4444,
}


# ----------------------------------------------------------------------
# Resolution des placeholders {state:..} {attr:..} {unit:..}
# ----------------------------------------------------------------------
# Syntaxe :
#   {state:sensor.xxx}            -> etat brut (str(state))
#   {state:sensor.xxx|--}         -> avec fallback si indisponible
#   {attr:sensor.xxx:friendly_name}
#   {attr:sensor.xxx:friendly_name|--}
#   {unit:sensor.xxx}             -> unit_of_measurement
PLACEHOLDER_RE = re.compile(
    r"\{(state|attr|unit):([a-zA-Z0-9_.]+)(?::([a-zA-Z0-9_]+))?(?:\|([^}]*))?\}"
)

# Variables dynamiques envoyees via l'API : {var:nom} ou {var:nom|valeur_par_defaut}
VAR_RE = re.compile(r"\{var:([a-zA-Z0-9_]+)(?:\|([^}]*))?\}")


def _resolve_vars(template: str, variables: dict | None) -> str:
    """Remplace les {var:nom} par les valeurs fournies via l'API.

    {var:nom}            -> valeur, ou '' si absente
    {var:nom|defaut}     -> valeur, ou 'defaut' si absente
    """
    if not template or "{var:" not in template:
        return template
    variables = variables or {}

    def replace(match: re.Match) -> str:
        name = match.group(1)
        fallback = match.group(2) if match.group(2) is not None else ""
        value = variables.get(name)
        return str(value) if value is not None else fallback

    return VAR_RE.sub(replace, template)


async def _resolve_template(
    template: str, variables: dict | None = None, resolve_vars: bool = True
) -> str:
    """Remplace les placeholders dans une string.

    Trois syntaxes supportees :
      0. Variables API (remplacees en premier, sans round-trip) :
         {var:nom}  {var:nom|defaut}
      1. Syntaxe BotPanel (rapide, no round-trip si pas utilisee) :
         {state:sensor.x}  {state:sensor.x|--}
         {attr:sensor.x:friendly_name}  {unit:sensor.x}
      2. Syntaxe Jinja Home Assistant (envoyee a /api/template) :
         {{ states('sensor.x') }}
         {{ state_attr('sensor.x', 'attr') }}
         {% if ... %}...{% endif %}

    Si plusieurs sont presentes : on resout d'abord les variables API, puis les
    placeholders BotPanel, puis on envoie le resultat a HA pour le Jinja restant.
    """
    if not template or "{" not in template:
        return template

    # 1) Resolution des placeholders BotPanel (rapide, fetch en local)
    if PLACEHOLDER_RE.search(template):
        entities: dict[str, dict | None] = {}
        for match in PLACEHOLDER_RE.finditer(template):
            entity_id = match.group(2)
            if entity_id not in entities:
                entities[entity_id] = None

        for entity_id in entities:
            try:
                entities[entity_id] = await ha_client.get_state(entity_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("HA get_state(%s) a echoue : %s", entity_id, exc)
                entities[entity_id] = None

        def replace(match: re.Match) -> str:
            kind = match.group(1)
            entity_id = match.group(2)
            attr = match.group(3)
            fallback = match.group(4) if match.group(4) is not None else "?"
            state = entities.get(entity_id)
            if state is None:
                return fallback
            if kind == "state":
                return str(state.get("state", fallback))
            if kind == "unit":
                return str(state.get("attributes", {}).get("unit_of_measurement", fallback))
            if kind == "attr":
                if not attr:
                    return fallback
                value = state.get("attributes", {}).get(attr)
                return str(value) if value is not None else fallback
            return fallback

        template = PLACEHOLDER_RE.sub(replace, template)

    # 2) Si la string contient encore du Jinja HA, on demande a HA de la rendre.
    if "{{" in template or "{%" in template:
        try:
            template = await ha_client.render_template(template)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rendu Jinja HA echoue : %s", exc)

    # 3) Variables dynamiques fournies par l'API — remplacees EN DERNIER pour que
    # leur contenu (potentiellement du texte externe, ex. un log de backup Proxmox)
    # ne soit PAS re-interprete comme un placeholder/Jinja.
    # (resolve_vars=False pour l'apercu editeur : on garde les {var:...} visibles.)
    if resolve_vars:
        template = _resolve_vars(template, variables)

    return template


# ----------------------------------------------------------------------
# Construction de l'embed
# ----------------------------------------------------------------------
_FR_MONTHS = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


def _format_fr_datetime(now: dt.datetime) -> str:
    """Renvoie une date FR absolue : '28 avril 2026 a 14:05'.

    On evite le rendu Discord auto ('aujourd'hui a ...') en n'utilisant
    pas `embed.timestamp` mais en injectant la date directement dans le footer.
    """
    return f"{now.day} {_FR_MONTHS[now.month - 1]} {now.year} a {now:%H:%M}"


# Limites imposees par l'API Discord sur un embed (au-dela -> 400/500).
_LIM_TITLE, _LIM_DESC, _LIM_FNAME, _LIM_FVALUE, _LIM_FOOTER = 256, 4096, 256, 1024, 2048
_LIM_TOTAL, _LIM_FIELDS = 6000, 25


def _clip(text: str, limit: int) -> str:
    """Tronque un texte a `limit` caracteres (ajoute … si coupe)."""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


async def build_embed(notif: Notification, variables: dict | None = None) -> discord.Embed:
    """Construit l'embed Discord d'une notification (resolution des placeholders incluse).

    `variables` : dictionnaire optionnel fourni via l'API pour remplir les {var:nom}
    dans le titre, le message et les champs. Toutes les parties sont bornees aux
    limites Discord (un message tres long — ex. backup multi-VM Proxmox — ne fait
    plus echouer l'envoi).
    """
    title = _clip(await _resolve_template(notif.title, variables), _LIM_TITLE)
    description = _clip(await _resolve_template(notif.message, variables), _LIM_DESC)

    embed = discord.Embed(
        title=title,
        description=description,
        color=notif.color,
    )
    # Budget total de l'embed (6000). On decompte au fur et a mesure et on
    # s'arrete d'ajouter des champs si on approche la limite.
    used = len(title) + len(description)
    # L'URL de l'image (miniature) supporte aussi les {var:...} et placeholders,
    # ex. une affiche de film/serie envoyee via l'API.
    icon_url = await _resolve_template(notif.icon_url, variables) if notif.icon_url else ""
    if icon_url and icon_url.strip():
        embed.set_thumbnail(url=icon_url.strip())

    # Grande image (affichee en grand sous le texte), variables supportees.
    image_url = await _resolve_template(notif.image_url, variables) if notif.image_url else ""
    if image_url and image_url.strip():
        embed.set_image(url=image_url.strip())

    # Footer = footer texte + (optionnel) date absolue.
    footer_parts: list[str] = []
    if notif.footer:
        footer_parts.append(await _resolve_template(notif.footer, variables))
    if notif.show_timestamp:
        footer_parts.append(_format_fr_datetime(dt.datetime.now()))
    if footer_parts:
        footer_text = _clip(" \u00b7 ".join(footer_parts), _LIM_FOOTER)
        embed.set_footer(text=footer_text)
        used += len(footer_text)

    # Fields custom (resolution des placeholders dans le nom ET la valeur).
    # On respecte le max de 25 champs et le budget total de 6000 caracteres.
    for fld in sorted(notif.fields, key=lambda f: (f.position, f.id or 0)):
        if len(embed.fields) >= _LIM_FIELDS:
            break
        name = _clip(await _resolve_template(fld.name, variables), _LIM_FNAME) or "\u200b"
        value = _clip(await _resolve_template(fld.value_template, variables), _LIM_FVALUE) or "\u200b"
        if used + len(name) + len(value) > _LIM_TOTAL:
            break
        used += len(name) + len(value)
        embed.add_field(name=name, value=value, inline=fld.inline)

    return embed


async def _resolve_channel(channel_id: str) -> discord.abc.Messageable | None:
    """Recupere un channel Discord par son ID (cache ou fetch)."""
    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        logger.error("channel_id invalide : %r", channel_id)
        return None
    channel = bot.get_channel(cid)
    if channel is None:
        try:
            channel = await bot.fetch_channel(cid)
        except discord.HTTPException as exc:
            logger.error("Impossible de fetch le channel %s : %s", cid, exc)
            return None
    return channel  # type: ignore[return-value]


async def send_notification(
    slug: str, variables: dict | None = None, source: str | None = None
) -> discord.Message | None:
    """Envoie la notification identifiee par `slug` dans son channel Discord.

    `variables` : valeurs dynamiques optionnelles (API) pour les {var:nom}.
    `source`    : origine de l'envoi (ex. "home_assistant", "api", "manuel").
    """
    repo = NotificationRepository()
    notif = await repo.get_by_slug(slug)
    if notif is None:
        logger.warning("Notification inconnue : %s", slug)
        return None
    return await send_notification_object(notif, variables, source=source)


async def _get_or_create_thread(
    channel: discord.TextChannel, group_name: str
) -> discord.Thread:
    """Retourne le thread Discord actif pour ce groupe, ou en cree un nouveau."""
    from app.db.repositories.threads import ThreadRepository

    repo = ThreadRepository()
    stored_id = await repo.get_thread_id(group_name, str(channel.id))

    if stored_id:
        try:
            existing = await bot.fetch_channel(int(stored_id))
            if isinstance(existing, discord.Thread):
                if existing.archived:
                    await existing.edit(archived=False)
                return existing
        except (discord.NotFound, discord.HTTPException):
            pass

    thread = await channel.create_thread(
        name=group_name,
        auto_archive_duration=10080,
        type=discord.ChannelType.public_thread,
    )
    await repo.upsert(group_name, str(channel.id), str(thread.id))
    logger.info("Thread '%s' cree (id=%s) dans #%s", group_name, thread.id, channel.id)
    return thread


async def _send_to_forum(
    forum: discord.ForumChannel,
    group_name: str,
    embed: discord.Embed,
    view,
    mention: str | None = None,
) -> tuple[discord.Message, str]:
    """Envoie dans un post forum existant ou en cree un nouveau.

    Retourne (message, detail_log).
    - Post existant (DB ou scan) : envoi comme reponse dans le thread.
    - Nouveau post : le premier embed est le message d'ouverture du post.
    """
    from app.db.repositories.threads import ThreadRepository

    repo = ThreadRepository()
    stored_id = await repo.get_thread_id(group_name, str(forum.id))

    if stored_id:
        try:
            thread = await bot.fetch_channel(int(stored_id))
            if isinstance(thread, discord.Thread):
                if thread.archived:
                    await thread.edit(archived=False)
                msg = await thread.send(content=mention, embed=embed, view=view)
                return msg, f"forum:{group_name}"
        except (discord.NotFound, discord.HTTPException):
            pass

    # Recherche dans les posts actifs par nom
    for t in forum.threads:
        if t.name == group_name and not t.archived:
            await repo.upsert(group_name, str(forum.id), str(t.id))
            msg = await t.send(content=mention, embed=embed, view=view)
            return msg, f"forum:{group_name}"

    # Creation d'un nouveau post — l'embed est le message d'ouverture
    result = await forum.create_thread(
        name=group_name,
        content=mention,
        embed=embed,
        view=view,
        auto_archive_duration=10080,
    )
    await repo.upsert(group_name, str(forum.id), str(result.thread.id))
    logger.info("Post forum '%s' cree (id=%s) dans #%s", group_name, result.thread.id, forum.id)
    return result.message, f"forum_new:{group_name}"


async def send_notification_object(
    notif: Notification, variables: dict | None = None, source: str | None = None
) -> discord.Message | None:
    """Envoie une notification selon son thread_mode.

    - none   : envoi direct dans le channel
    - thread : envoi dans un fil du channel texte (cree/recupere par group_name)
    - forum  : envoi dans un post du channel forum (cree/recupere par group_name)
    Les tests et previews (notif.id == 0) ignorent thread/forum et vont dans le channel.

    `variables` : valeurs dynamiques optionnelles (API) pour les {var:nom}.
    """
    channel_id = notif.channel_id or str(settings.discord_default_channel_id)
    channel = await _resolve_channel(channel_id)
    log_repo = LogRepository()
    # Origine de l'envoi (pour l'historique) : fournie par l'appelant, sinon
    # "test" pour un apercu (id=0), "manuel" pour un envoi normal.
    src = source or ("test" if not notif.id else "manuel")

    if channel is None:
        await log_repo.add(
            kind="send",
            notification_id=notif.id or None,
            notification_slug=notif.slug,
            channel_id=channel_id,
            success=False,
            detail=f"Channel {channel_id} introuvable",
            source=src,
        )
        return None

    embed = await build_embed(notif, variables)
    view = build_notification_view(notif)

    message: discord.Message | None = None
    log_detail: str | None = "ephemere (test)" if not notif.id else None
    use_mode = notif.thread_mode if (notif.id and notif.group_name) else "none"

    mention_content: str | None = notif.mention or None

    try:
        if use_mode == "forum" and isinstance(channel, discord.ForumChannel):
            message, log_detail = await _send_to_forum(
                channel, notif.group_name, embed, view, mention_content  # type: ignore[arg-type]
            )

        elif use_mode == "thread" and isinstance(channel, discord.TextChannel):
            thread = await _get_or_create_thread(channel, notif.group_name)  # type: ignore[arg-type]
            message = await thread.send(content=mention_content, embed=embed, view=view)
            log_detail = f"thread:{notif.group_name}"

        else:
            message = await channel.send(content=mention_content, embed=embed, view=view)

    except discord.HTTPException as exc:
        logger.error("Echec envoi notification %s : %s", notif.slug, exc)
        await log_repo.add(
            kind="send",
            notification_id=notif.id or None,
            notification_slug=notif.slug,
            channel_id=channel_id,
            success=False,
            detail=str(exc)[:300],
            source=src,
        )
        return None

    logger.info("Notification '%s' envoyee [mode=%s] (msg=%s)", notif.slug, use_mode, message.id)
    await log_repo.add(
        kind="send",
        notification_id=notif.id or None,
        notification_slug=notif.slug,
        channel_id=channel_id,
        message_id=str(message.id),
        success=True,
        detail=log_detail,
        source=src,
    )
    return message
