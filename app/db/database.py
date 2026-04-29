"""Gestion de la connexion SQLite et initialisation du schema."""

from __future__ import annotations

import logging
import sqlite3
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
-- CHAMPS (FIELDS) D'UNE NOTIFICATION
-- Affiches dans l'embed Discord. value_template peut contenir
-- des placeholders resolus au moment de l'envoi :
--   {state:sensor.xxx}             -> etat brut
--   {state:sensor.xxx|--}          -> avec fallback si indisponible
--   {attr:sensor.xxx:friendly_name}
--   {unit:sensor.xxx}              -> unit_of_measurement
-- ==========================================================
CREATE TABLE IF NOT EXISTS notification_fields (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id INTEGER NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0,
    name            TEXT NOT NULL,                    -- intitule du field
    value_template  TEXT NOT NULL,                    -- texte avec placeholders
    inline          INTEGER NOT NULL DEFAULT 1,       -- 0/1
    FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fields_notif
    ON notification_fields(notification_id);

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
-- N blocs custom (creation libre depuis le site).
-- Chaque bloc = un message Discord epingle, edite a intervalle regulier.
-- config_json : { "fields": [{label, icon, entity_id, attribute, suffix, inline}, ...] }
-- ==========================================================
CREATE TABLE IF NOT EXISTS monitoring_blocks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL DEFAULT 'Bloc',
    icon            TEXT,                             -- emoji ou URL
    color           INTEGER NOT NULL DEFAULT 4827743, -- 0x49A0DF (bleu) par defaut
    enabled         INTEGER NOT NULL DEFAULT 0,
    channel_id      TEXT,
    message_id      TEXT,
    interval_seconds INTEGER NOT NULL DEFAULT 300,
    footer          TEXT,
    config_json     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ==========================================================
-- SETTINGS (key/value JSON)
-- Stocke les preferences globales : presets de couleurs,
-- presets de channels, etc.
-- ==========================================================
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value_json      TEXT NOT NULL DEFAULT '[]',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# Liste des ALTER TABLE pour migrer les bases existantes (avant la refonte
# multi-blocs). Idempotents : on ignore l'erreur si la colonne existe deja.
_MIGRATIONS_ALTER: list[str] = [
    "ALTER TABLE monitoring_blocks ADD COLUMN name TEXT NOT NULL DEFAULT 'Bloc'",
    "ALTER TABLE monitoring_blocks ADD COLUMN icon TEXT",
    "ALTER TABLE monitoring_blocks ADD COLUMN color INTEGER NOT NULL DEFAULT 4827743",
    "ALTER TABLE monitoring_blocks ADD COLUMN footer TEXT",
    "ALTER TABLE monitoring_blocks ADD COLUMN created_at TEXT",
]


async def _migrate(db: aiosqlite.Connection) -> None:
    """Migrations douces pour bases pre-refonte (passage block_type fixe -> N blocs libres)."""
    # 1) Ajout colonnes manquantes (idempotent)
    for sql in _MIGRATIONS_ALTER:
        try:
            await db.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                logger.warning("Migration ignoree (%s) : %s", sql, exc)

    # 2) Supprimer la contrainte UNIQUE sur block_type si presente.
    cursor = await db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='monitoring_blocks'"
    )
    row = await cursor.fetchone()
    create_sql = (row[0] or "") if row else ""
    if "block_type" in create_sql:
        # On reconstruit la table sans block_type (devient juste un name backfille).
        logger.info("Migration monitoring_blocks : suppression du block_type fixe.")
        await db.executescript(
            """
            CREATE TABLE monitoring_blocks_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL DEFAULT 'Bloc',
                icon            TEXT,
                color           INTEGER NOT NULL DEFAULT 4827743,
                enabled         INTEGER NOT NULL DEFAULT 0,
                channel_id      TEXT,
                message_id      TEXT,
                interval_seconds INTEGER NOT NULL DEFAULT 300,
                footer          TEXT,
                config_json     TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO monitoring_blocks_new (
                id, name, icon, color, enabled, channel_id, message_id,
                interval_seconds, footer, config_json, updated_at
            )
            SELECT
                id,
                COALESCE(NULLIF(name, ''), block_type, 'Bloc'),
                icon,
                COALESCE(color, 4827743),
                enabled,
                channel_id,
                message_id,
                interval_seconds,
                footer,
                COALESCE(config_json, '{}'),
                COALESCE(updated_at, datetime('now'))
            FROM monitoring_blocks;
            DROP TABLE monitoring_blocks;
            ALTER TABLE monitoring_blocks_new RENAME TO monitoring_blocks;
            """
        )


async def init_db() -> None:
    """Cree le fichier SQLite et applique le schema s'il n'existe pas."""
    db_path = settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(SCHEMA)
        await _migrate(db)
        await db.commit()

    logger.info("Base SQLite initialisee : %s", db_path)


@asynccontextmanager
async def get_connection() -> AsyncIterator[aiosqlite.Connection]:
    """Context manager qui fournit une connexion SQLite configuree."""
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        yield db
