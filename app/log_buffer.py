"""Mémoire tampon des derniers avertissements / erreurs du serveur.

Un handler `logging` garde en RAM les N derniers messages de niveau WARNING
et plus (perdus au redémarrage). Lu par l'outil MCP `list_errors`, pour que
Claude puisse voir les erreurs sans accès au journal système.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections import deque

MAX_RECORDS = 200

_records: deque[dict] = deque(maxlen=MAX_RECORDS)


class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                msg = f"{msg} — {type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
            _records.append({
                "time": dt.datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": msg[:1000],
            })
        except Exception:  # noqa: BLE001 — ne jamais casser le logging
            pass


_handler = _BufferHandler(level=logging.WARNING)


def install() -> None:
    """Branche le handler sur le logger racine (idempotent)."""
    root = logging.getLogger()
    if _handler not in root.handlers:
        root.addHandler(_handler)


def recent(limit: int = 50) -> list[dict]:
    """Les `limit` derniers messages, du plus récent au plus ancien."""
    return list(reversed(_records))[:limit]
