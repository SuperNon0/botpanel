"""Export / import de toutes les donnees de configuration.

Permet de sauvegarder l'ensemble des notifications, commandes, blocs de
monitoring et parametres dans un fichier JSON, puis de les re-importer sur
une autre instance de BotPanel (migration).

Les journaux (historique) et les etats runtime Discord (threads/posts) ne
sont PAS exportes : ce sont des donnees propres a une instance.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.db.database import get_connection

logger = logging.getLogger(__name__)
router = APIRouter()

# Tables exportees, dans un ordre qui respecte les cles etrangeres a l'import
# (les notifications avant leurs boutons/fields).
EXPORT_TABLES: list[str] = [
    "notifications",
    "notification_buttons",
    "notification_fields",
    "slash_commands",
    "monitoring_blocks",
    "settings",
]

EXPORT_FORMAT = "botpanel-export/1"


async def _table_columns(db, table: str) -> list[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return [r["name"] for r in rows]


@router.get("/export")
async def export_data() -> JSONResponse:
    """Renvoie toutes les donnees de configuration en JSON (telechargeable)."""
    data: dict[str, list[dict]] = {}
    async with get_connection() as db:
        for table in EXPORT_TABLES:
            try:
                rows = await db.execute_fetchall(f"SELECT * FROM {table}")
                data[table] = [dict(r) for r in rows]
            except Exception as exc:  # noqa: BLE001 — table absente sur vieille base
                logger.warning("Export : table %s ignoree (%s)", table, exc)
                data[table] = []

    payload = {"format": EXPORT_FORMAT, "tables": data}
    counts = ", ".join(f"{t}={len(v)}" for t, v in data.items())
    logger.info("Export effectue : %s", counts)
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="botpanel-export.json"'},
    )


@router.post("/import")
async def import_data(request: Request) -> dict[str, object]:
    """Importe des donnees depuis un export JSON.

    ATTENTION : remplace entierement les donnees de configuration existantes
    (notifications, commandes, monitoring, parametres). A utiliser sur une
    nouvelle instance ou pour restaurer une sauvegarde.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Fichier JSON invalide.")

    if not isinstance(payload, dict) or "tables" not in payload:
        raise HTTPException(status_code=400, detail="Format d'export non reconnu.")

    tables = payload["tables"]
    if not isinstance(tables, dict):
        raise HTTPException(status_code=400, detail="Champ 'tables' invalide.")

    # On ignore toute table inconnue (securite) et on garde l'ordre FK.
    imported: dict[str, int] = {}
    async with get_connection() as db:
        try:
            # Purge des tables de config (l'ordre inverse evite les soucis FK ;
            # de toute facon ON DELETE CASCADE nettoie les boutons/fields).
            for table in reversed(EXPORT_TABLES):
                await db.execute(f"DELETE FROM {table}")

            for table in EXPORT_TABLES:
                rows = tables.get(table) or []
                if not isinstance(rows, list):
                    continue
                valid_cols = set(await _table_columns(db, table))
                count = 0
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    # Sur une nouvelle instance, l'ID de message Discord n'a plus
                    # de sens : le bot recreera le message de monitoring.
                    if table == "monitoring_blocks":
                        row = {**row, "message_id": None}
                    cols = [c for c in row.keys() if c in valid_cols]
                    if not cols:
                        continue
                    placeholders = ", ".join("?" for _ in cols)
                    col_list = ", ".join(cols)
                    values = [row[c] for c in cols]
                    await db.execute(
                        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                        values,
                    )
                    count += 1
                imported[table] = count

            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Echec de l'import : %s", exc)
            raise HTTPException(status_code=500, detail=f"Echec de l'import : {exc}")

    total = sum(imported.values())
    logger.info("Import effectue : %s (%d lignes)", imported, total)
    return {"status": "imported", "counts": imported, "total": total}
