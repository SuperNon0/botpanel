"""Routes d'authentification : login, logout, etat, gestion du mot de passe admin."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import (
    COOKIE_NAME,
    SESSION_TTL,
    auth_state,
    cf_access_email,
    cf_config,
    cf_diagnostic,
    create_session_token,
    current_user,
    hash_password,
    is_authenticated,
    normalize_team,
    verify_password,
)
from app.db.repositories import AuthRepository, SettingsRepository

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginPayload(BaseModel):
    username: str = "admin"
    password: str = Field(..., min_length=1)


class PasswordPayload(BaseModel):
    current_password: str = ""
    new_password: str = Field(..., min_length=6)
    username: str = "admin"


class DisablePayload(BaseModel):
    current_password: str = Field(..., min_length=1)


class CfConfigPayload(BaseModel):
    team: str = ""
    aud: str = ""
    verify: bool = True
    allow_local: bool = True


class CfTestPayload(BaseModel):
    team: str = ""
    aud: str = ""


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.get("/me")
async def me(request: Request) -> dict:
    """Etat de connexion : badge Cloudflare prioritaire, sinon session mot de passe."""
    state = await auth_state()
    who = await is_authenticated(request)
    if who is None:
        return {"enabled": state["enabled"], "authenticated": False,
                "method": None, "email": None, "username": None}
    return {
        "enabled": state["enabled"],
        "authenticated": True,
        "method": who["method"],            # "cloudflare" | "password"
        "email": who["email"],              # e-mail si connexion Cloudflare
        "username": who["username"],        # username si connexion mot de passe
    }


# ----------------------------------------------------------------------
# Cloudflare Access — config (UI) + test
# ----------------------------------------------------------------------
async def _require_admin_access(request: Request) -> None:
    """Respecte le mode local ouvert, le mot de passe et le mode Cloudflare seul."""
    cfg = await cf_config()
    if cfg["allow_local"]:
        if not (await auth_state())["enabled"] or await current_user(request):
            return
    if await cf_access_email(request, require_verified=True):
        return
    raise HTTPException(401, "Connexion administrateur requise.")


@router.get("/cf-config")
async def get_cf_config(request: Request) -> dict:
    await _require_admin_access(request)
    return await cf_config()


@router.post("/cf-config")
async def save_cf_config(payload: CfConfigPayload, request: Request) -> dict:
    await _require_admin_access(request)
    team = normalize_team(payload.team)
    aud = payload.aud.strip()
    if payload.team.strip() and not team:
        raise HTTPException(422, "Nom d’équipe Cloudflare invalide.")
    if not payload.allow_local:
        if not payload.verify or not team or not aud:
            raise HTTPException(422, "Le mode Cloudflare uniquement exige un JWT vérifié, une équipe et un AUD.")
        diagnostic = await cf_diagnostic(request, team=team, aud=aud)
        if not diagnostic["jwt_email"]:
            raise HTTPException(422, "Connecte-toi via Cloudflare et valide le badge avant de couper l’accès local.")
    await SettingsRepository().set_many({
        "cf_team": team, "cf_aud": aud, "cf_verify": payload.verify, "cf_allow_local": payload.allow_local,
    })
    logger.info("Config Cloudflare enregistrée (team=%s, verify=%s, allow_local=%s)", team, payload.verify, payload.allow_local)
    return {"status": "ok"}


@router.post("/cf-test")
async def cf_test(payload: CfTestPayload, request: Request) -> dict:
    await _require_admin_access(request)
    if payload.team.strip() and not normalize_team(payload.team):
        raise HTTPException(422, "Nom d’équipe Cloudflare invalide.")
    return await cf_diagnostic(request, team=payload.team, aud=payload.aud)

@router.post("/login")
async def login(payload: LoginPayload, request: Request, response: Response) -> dict:
    # Mode « Cloudflare uniquement » : l'entree locale est refusee, meme en POST.
    cfg = await cf_config()
    if not cfg["allow_local"]:
        raise HTTPException(403, "Acces direct desactive (Cloudflare uniquement).")
    state = await auth_state()
    if not state["enabled"]:
        raise HTTPException(400, "La protection par mot de passe n'est pas activee.")
    if payload.username != state["username"] or not verify_password(payload.password, state["password_hash"]):
        raise HTTPException(401, "Identifiants incorrects.")

    secret = state["secret"] or await AuthRepository().get_or_create_secret(state["password_hash"])
    if secret is None:
        raise HTTPException(401, "Identifiants incorrects.")
    token = create_session_token(state["username"], secret)
    _set_cookie(response, request, token)
    logger.info("Connexion admin reussie (%s)", state["username"])
    return {"status": "ok", "username": state["username"]}


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.post("/password")
async def set_password(payload: PasswordPayload, request: Request, response: Response) -> dict:
    """Definit ou change le mot de passe admin.

    - Si la protection est desactivee : definit le 1er mot de passe (l'active).
    - Si elle est activee : exige le mot de passe actuel + une session valide.
    """
    await _require_admin_access(request)
    state = await auth_state()
    repo = AuthRepository()

    if state["enabled"]:
        if not verify_password(payload.current_password, state["password_hash"]):
            raise HTTPException(403, "Mot de passe actuel incorrect.")

    username = (payload.username or "admin").strip() or "admin"
    secret = await repo.set_password(hash_password(payload.new_password), username=username)
    token = create_session_token(username, secret)
    _set_cookie(response, request, token)
    logger.info("Mot de passe admin mis a jour (%s)", username)
    return {"status": "ok", "enabled": True, "username": username}


@router.post("/disable")
async def disable(payload: DisablePayload, request: Request, response: Response) -> dict:
    """Desactive la protection (panel ouvert). Exige le mot de passe actuel."""
    await _require_admin_access(request)
    state = await auth_state()
    if not state["enabled"]:
        return {"status": "ok", "enabled": False}
    if not verify_password(payload.current_password, state["password_hash"]):
        raise HTTPException(403, "Mot de passe incorrect.")
    repo = AuthRepository()
    await repo.clear_password()
    response.delete_cookie(COOKIE_NAME, path="/")
    logger.info("Protection par mot de passe desactivee.")
    return {"status": "ok", "enabled": False}
