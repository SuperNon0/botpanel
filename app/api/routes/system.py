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
    """git fetch + reset --hard + pip install, sans sudo.

    Prerequis : /opt/botpanel appartient a l'utilisateur qui fait tourner le service
    (botpanel). Une seule fois sur le serveur : chown -R botpanel:botpanel /opt/botpanel
    """
    if not (INSTALL_DIR / ".git").exists():
        raise HTTPException(400, f"{INSTALL_DIR} n'est pas un depot git.")

    branch_res = await _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=INSTALL_DIR, timeout=5
    )
    branch = branch_res["stdout"].strip() or "main"
    remote_ref = f"origin/{branch}"

    fetch = await _run(["git", "fetch", "--prune"], cwd=INSTALL_DIR, timeout=120)
    if fetch["exit_code"] != 0:
        return {
            "ok": False,
            "fetch": fetch,
            "pull": {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Abandonné — git fetch a échoué.",
                "command": f"git reset --hard {remote_ref}",
            },
        }

    pull = await _run(
        ["git", "reset", "--hard", remote_ref], cwd=INSTALL_DIR, timeout=60
    )

    # Mise a jour des dependances Python si le reset a reussi
    pip_result: dict | None = None
    venv_pip = INSTALL_DIR / ".venv" / "bin" / "pip"
    if pull["exit_code"] == 0 and venv_pip.exists():
        pip_result = await _run(
            [str(venv_pip), "install", "-q", "-r", str(INSTALL_DIR / "requirements.txt")],
            cwd=INSTALL_DIR,
            timeout=120,
        )

    return {"ok": pull["exit_code"] == 0, "fetch": fetch, "pull": pull, "pip": pip_result}


@router.post("/restart")
async def system_restart() -> dict:
    """Redémarre le service en quittant le process avec code 1.

    systemd (Restart=on-failure) relanc automatiquement le service apres RestartSec.
    L'API devient inaccessible quelques secondes ; le client doit poller /api/system/info.
    """

    async def _exit_after_response() -> None:
        await asyncio.sleep(0.4)
        os._exit(1)  # noqa: SLF001 — exit code 1 → systemd restart

    asyncio.create_task(_exit_after_response())
    return {"status": "restarting"}
