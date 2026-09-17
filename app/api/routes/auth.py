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
@router.get("/cf-config")
async def get_cf_config() -> dict:
    """Renvoie la config Cloudflare effective (equipe, aud, verif)."""
    return await cf_config()


@router.post("/cf-config")
async def save_cf_config(payload: CfConfigPayload, request: Request) -> dict:
    """Enregistre la config Cloudflare (equipe/AUD/verif) depuis les Parametres."""
    state = await auth_state()
    if state["enabled"] and await is_authenticated(request) is None:
        raise HTTPException(401, "Connexion requise.")
    repo = SettingsRepository()
    await repo.set("cf_team", normalize_team(payload.team))
    await repo.set("cf_aud", (payload.aud or "").strip())
    await repo.set("cf_verify", bool(payload.verify))
    logger.info("Config Cloudflare enregistree (team=%s, verify=%s)", normalize_team(payload.team), payload.verify)
    return {"status": "ok"}


@router.post("/cf-test")
async def cf_test(payload: CfTestPayload, request: Request) -> dict:
    """Teste en direct la connexion Cloudflare pour les valeurs saisies (bouton Tester)."""
    return await cf_diagnostic(request, team=payload.team, aud=payload.aud)


@router.post("/login")
async def login(payload: LoginPayload, request: Request, response: Response) -> dict:
    state = await auth_state()
    if not state["enabled"]:
        raise HTTPException(400, "La protection par mot de passe n'est pas activee.")
    if payload.username != state["username"] or not verify_password(payload.password, state["password_hash"]):
        raise HTTPException(401, "Identifiants incorrects.")

    repo = AuthRepository()
    secret = await repo.get_or_create_secret()
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
    state = await auth_state()
    repo = AuthRepository()

    if state["enabled"]:
        user = await current_user(request)
        if user is None:
            raise HTTPException(401, "Connexion requise pour changer le mot de passe.")
        if not verify_password(payload.current_password, state["password_hash"]):
            raise HTTPException(403, "Mot de passe actuel incorrect.")

    username = (payload.username or "admin").strip() or "admin"
    await repo.set_password(hash_password(payload.new_password), username=username)

    # (Re)genere une session valide pour l'utilisateur courant
    secret = await repo.get_or_create_secret()
    token = create_session_token(username, secret)
    _set_cookie(response, request, token)
    logger.info("Mot de passe admin mis a jour (%s)", username)
    return {"status": "ok", "enabled": True, "username": username}


@router.post("/disable")
async def disable(payload: DisablePayload, request: Request, response: Response) -> dict:
    """Desactive la protection (panel ouvert). Exige le mot de passe actuel."""
    state = await auth_state()
    if not state["enabled"]:
        return {"status": "ok", "enabled": False}
    user = await current_user(request)
    if user is None:
        raise HTTPException(401, "Connexion requise.")
    if not verify_password(payload.current_password, state["password_hash"]):
        raise HTTPException(403, "Mot de passe incorrect.")
    repo = AuthRepository()
    await repo.clear_password()
    response.delete_cookie(COOKIE_NAME, path="/")
    logger.info("Protection par mot de passe desactivee.")
    return {"status": "ok", "enabled": False}
