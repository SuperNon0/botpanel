"""Routes d'authentification : login, logout, etat, gestion du mot de passe admin."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import (
    COOKIE_NAME,
    SESSION_TTL,
    auth_state,
    create_session_token,
    current_user,
    hash_password,
    verify_password,
)
from app.db.repositories import AuthRepository

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
    state = await auth_state()
    user = await current_user(request)
    return {
        "enabled": state["enabled"],
        "authenticated": user is not None,
        "username": user,
    }


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
