"""SQLite-backed session store.

The browser only ever holds an opaque, signed session id. Canvas access tokens
stay on the server so they are never exposed to the frontend.
"""

from __future__ import annotations

import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    canvas_user_id INTEGER,
    canvas_user_name TEXT,
    canvas_user_email TEXT,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
"""


@dataclass(frozen=True)
class Session:
    id: str
    canvas_user_id: int | None
    canvas_user_name: str | None
    canvas_user_email: str | None
    access_token: str
    refresh_token: str | None
    created_at: int
    last_seen_at: int
    expires_at: int


def _connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with closing(_connect()) as connection, connection:
        connection.executescript(SCHEMA)


def create_session(
    *,
    canvas_user_id: int | None,
    canvas_user_name: str | None,
    canvas_user_email: str | None,
    access_token: str,
    refresh_token: str | None = None,
) -> str:
    session_id = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + settings.session_max_age
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO sessions (
                id, canvas_user_id, canvas_user_name, canvas_user_email,
                access_token, refresh_token, created_at, last_seen_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                canvas_user_id,
                canvas_user_name,
                canvas_user_email,
                access_token,
                refresh_token,
                now,
                now,
                expires_at,
            ),
        )
    return session_id


def get_session(session_id: str) -> Session | None:
    now = int(time.time())
    with closing(_connect()) as connection, connection:
        row = connection.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        if row["expires_at"] <= now:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return None
        connection.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now, session_id)
        )
        return Session(**dict(row))


def delete_session(session_id: str) -> None:
    with closing(_connect()) as connection, connection:
        connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def purge_expired() -> int:
    now = int(time.time())
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM sessions WHERE expires_at <= ?", (now,)
        )
        return cursor.rowcount
