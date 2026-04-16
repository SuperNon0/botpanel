"""Gestion de la connexion SQLite et initialisation du schema."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

from app.config import settings

logger = logging.getLogger(__name__)


SCHEMA = """
-- ==========================================================
-- NOTIFICATIONS
-- Chaque notification est identifiee par un slug unique
-- appele depuis HA via rest_command.
-- ==========================================================
CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL UNIQUE,             -- ex: notif_porte_entree
    channel_id      TEXT NOT NULL,                    -- channel Discord cible
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    color           INTEGER NOT NULL DEFAULT 16776960,-- couleur embed (0xFFFF00)
    icon_url        TEXT,                             -- thumbnail optionnel
    footer          TEXT,
    show_timestamp  INTEGER NOT NULL DEFAULT 0,       -- 0/1
    delete_button   INTEGER NOT NULL DEFAULT 0,       -- 0/1
    snooze_button   INTEGER NOT NULL DEFAULT 0,       -- 0/1
    snooze_minutes  INTEGER NOT NULL DEFAULT 15,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ==========================================================
-- BOUTONS CUSTOM D'UNE NOTIFICATION
-- Chaque bouton declenche un service HA a son clic.
-- ==========================================================
CREATE TABLE IF NOT EXISTS notification_buttons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id INTEGER NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0,
    label           TEXT NOT NULL,
    style           TEXT NOT NULL DEFAULT 'primary',  -- primary/secondary/success/danger
    emoji           TEXT,
    ha_service      TEXT NOT NULL,                    -- ex: light.turn_on
    ha_entity_id    TEXT,                             -- ex: light.salon
    ha_data_json    TEXT,                             -- payload extra JSON
    FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_buttons_notif
    ON notification_buttons(notification_id);

-- ==========================================================
-- COMMANDES SLASH DISCORD
-- Gerees depuis le site, re-synchronisees avec Discord a chaque modif.
-- ==========================================================
CREATE TABLE IF NOT EXISTS slash_commands (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,             -- ex: allumer_salon
    description     TEXT NOT NULL,
    action_type     TEXT NOT NULL,                    -- service|script|scene|notification
    ha_service      TEXT,                             -- si action_type=service
    ha_entity_id    TEXT,
    ha_data_json    TEXT,                             -- payload JSON extra
    notification_slug TEXT,                           -- si action_type=notification
    response_message TEXT NOT NULL DEFAULT 'OK',      -- message ephemere de confirmation
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ==========================================================
-- BLOCS DE MONITORING
-- Un message Discord epingle par bloc, edite a intervalle regulier.
-- ==========================================================
CREATE TABLE IF NOT EXISTS monitoring_blocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    block_type      TEXT NOT NULL UNIQUE,             -- temperature|power
    enabled         INTEGER NOT NULL DEFAULT 0,
    channel_id      TEXT,                             -- channel Discord (sinon celui du .env)
    message_id      TEXT,                             -- id du message epingle
    interval_seconds INTEGER NOT NULL DEFAULT 300,
    config_json     TEXT NOT NULL DEFAULT '{}',       -- entites HA + libelles
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Blocs presents par defaut (desactives)
INSERT OR IGNORE INTO monitoring_blocks (block_type, enabled, config_json)
    VALUES
        ('temperature', 0, '{"sensors": []}'),
        ('power',       0, '{"entity_id": null}');
"""


async def init_db() -> None:
    """Cree le fichier SQLite et applique le schema s'il n'existe pas."""
    db_path = settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(SCHEMA)
        await db.commit()

    logger.info("Base SQLite initialisee : %s", db_path)


@asynccontextmanager
async def get_connection() -> AsyncIterator[aiosqlite.Connection]:
    """Context manager qui fournit une connexion SQLite configuree."""
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
