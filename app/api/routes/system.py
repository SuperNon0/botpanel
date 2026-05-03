"""Operations systeme : mise a jour git + redemarrage du service.

Necessite que le user 'botpanel' ait une regle sudoers du genre :
    botpanel ALL=NOPASSWD: /bin/systemctl restart botpanel
sinon le restart echoue avec un message explicatif.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


# Dossier d'installation : on remonte depuis ce fichier (app/api/routes/system.py)
# jusqu'a la racine du projet (4 niveaux : routes -> api -> app -> root).
INSTALL_DIR = Path(__file__).resolve().parents[3]


async def _run(cmd: list[str], cwd: Path | None = None, timeout: float = 60.0) -> dict:
    """Exec un process et collecte stdout/stderr/exit_code."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, "LC_ALL": "C"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"exit_code": -1, "stdout": "", "stderr": "Timeout depasse"}
    return {
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "command": " ".join(shlex.quote(c) for c in cmd),
    }


@router.get("/info")
async def system_info() -> dict:
    """Renvoie quelques infos pour la page des parametres."""
    info: dict = {"install_dir": str(INSTALL_DIR), "is_git": (INSTALL_DIR / ".git").exists()}
    if info["is_git"]:
        rev = await _run(["git", "rev-parse", "--short", "HEAD"], cwd=INSTALL_DIR, timeout=5)
        branch = await _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=INSTALL_DIR, timeout=5)
        info["commit"] = rev["stdout"].strip()
        info["branch"] = branch["stdout"].strip()
    return info


@router.post("/update")
async def system_update() -> dict:
    """Lance un `git fetch && git pull --ff-only`.

    Le redemarrage du service est expose separement (POST /system/restart)
    pour donner a l'UI le temps d'afficher le diff avant redemarrage.
    """
    if not (INSTALL_DIR / ".git").exists():
        raise HTTPException(400, f"{INSTALL_DIR} n'est pas un depot git.")

    fetch = await _run(["git", "fetch", "--prune"], cwd=INSTALL_DIR, timeout=120)
    if fetch["exit_code"] != 0:
        return {"step": "fetch", **fetch, "ok": False}

    pull = await _run(["git", "pull", "--ff-only"], cwd=INSTALL_DIR, timeout=120)
    return {
        "step": "pull",
        "ok": pull["exit_code"] == 0,
        "fetch": fetch,
        "pull": pull,
    }


@router.post("/restart")
async def system_restart() -> dict:
    """Lance `sudo systemctl restart botpanel` en detache (le process se suicide).

    L'API va devenir inaccessible quelques secondes ; le client doit poller /health.
    """
    cmd = ["sudo", "-n", "/bin/systemctl", "restart", "botpanel"]
    # On lance en detache pour que le restart survive a la mort de notre process
    try:
        await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(500, f"Commande introuvable : {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Erreur lors du lancement du restart : {exc}") from exc
    return {"status": "restarting"}
