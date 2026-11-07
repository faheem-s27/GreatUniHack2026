"""SQLite connection helper.

Uses the standard-library sqlite3 module so no extra dependency is needed.
The database path can be overridden with LOSTPOINT_DB (tests use a temp file).
"""

import os
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS lost_moments (
    id            TEXT PRIMARY KEY,
    student_id    TEXT NOT NULL,
    lecture_id    TEXT NOT NULL,
    slide_number  INTEGER NOT NULL,
    topic         TEXT,
    lecture_time_s INTEGER,
    created_at    TEXT NOT NULL,
    resolved      INTEGER NOT NULL DEFAULT 0,
    resolved_at   TEXT,
    screenshot    BLOB,
    screenshot_type TEXT
);
CREATE INDEX IF NOT EXISTS idx_lost_student ON lost_moments(student_id, created_at);
CREATE INDEX IF NOT EXISTS idx_lost_lecture ON lost_moments(lecture_id, slide_number);
"""


def db_path() -> str:
    return os.environ.get("LOSTPOINT_DB", os.path.join(os.path.dirname(__file__), "lostpoint.db"))


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
