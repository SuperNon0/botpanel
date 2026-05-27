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
    """Appelle deploy/update.sh --no-restart via sudo (tourne en root → pas de problème de permissions git)."""
    script = INSTALL_DIR / "deploy" / "update.sh"
    if not script.exists():
        raise HTTPException(400, f"Script introuvable : {script}")

    result = await _run(
        ["sudo", "-n", "bash", str(script), "--no-restart"],
        cwd=INSTALL_DIR,
        timeout=180,
    )
    output = (result["stdout"] + result["stderr"]).strip()
    ok = result["exit_code"] == 0
    return {
        "ok": ok,
        "fetch": {
            "command": "sudo bash deploy/update.sh --no-restart",
            "stdout": output,
            "stderr": "" if ok else output,
            "exit_code": result["exit_code"],
        },
        "pull": {
            "command": "git reset --hard origin/main",
            "stdout": "OK" if ok else "",
            "stderr": "",
            "exit_code": result["exit_code"],
        },
    }


@router.post("/restart")
async def system_restart() -> dict:
    """Lance `sudo systemctl restart botpanel` en detache.

    Attend 2 s pour capturer les echecs immediats (droits sudo manquants, etc.).
    L'API devient inaccessible quelques secondes ; le client doit poller /api/system/info.
    """
    import shutil  # noqa: PLC0415

    systemctl = shutil.which("systemctl") or "/bin/systemctl"
    cmd = ["sudo", "-n", systemctl, "restart", "botpanel"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            # Si on arrive ici le process s'est termine avant 2 s → echec
            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace").strip()
                raise HTTPException(
                    500,
                    err or f"systemctl a retourne le code {proc.returncode}. "
                    "Vérifiez la règle sudoers : "
                    f"botpanel ALL=NOPASSWD: {systemctl} restart botpanel",
                )
        except asyncio.TimeoutError:
            pass  # Normal — le service est en train de redemarrer
    except FileNotFoundError as exc:
        raise HTTPException(500, f"Commande introuvable : {exc}") from exc
    return {"status": "restarting"}
