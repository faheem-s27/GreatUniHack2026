"""SQLite connection helper and schema.

Uses the standard-library sqlite3 module so no extra dependency is needed.
The database path can be overridden with LOSTPOINT_DB (tests use a temp file).

Tables
  lost_moments      one "I'm lost" tap (lost_moments.py)
  courses           a module, e.g. Calculus 1 (courses.py)
  lectures          one lecture in a course, by week
  slides            slide text (and optional image) per lecture; slides_fts
                    is a full-text index over it, used for search with
                    slide-number citations until Chroma takes over
  coursework        assessed work per course; the coach's locked mode checks
                    questions against it (coursework.py)
  gaps              student memory: an idea a student keeps struggling with,
                    optionally traced back to an earlier root gap (memory.py)
  gap_moments       which lost moments are evidence for which gap
  coach_sessions    one coach conversation, with the mode decided in code
  coach_messages    the messages in it, with slide citations (coach_store.py)
  lecture_attendance  who joined a live lecture, so the heatmap can show
                    "% of the room" (live.py). Captions are never stored.

Every statement is CREATE ... IF NOT EXISTS, so an existing lostpoint.db
gains the new tables on the next start without losing data.
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

CREATE TABLE IF NOT EXISTS courses (
    id          TEXT PRIMARY KEY,
    code        TEXT,
    title       TEXT NOT NULL,
    term        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lectures (
    id          TEXT PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    week        INTEGER,
    title       TEXT NOT NULL,
    held_at     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lectures_course ON lectures(course_id, week);

CREATE TABLE IF NOT EXISTS slides (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id    TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
    slide_number  INTEGER NOT NULL,
    title         TEXT,
    topic         TEXT,
    body          TEXT NOT NULL DEFAULT '',
    image         BLOB,
    image_type    TEXT,
    UNIQUE (lecture_id, slide_number)
);

CREATE VIRTUAL TABLE IF NOT EXISTS slides_fts USING fts5(
    title, topic, body, content='slides', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS slides_ai AFTER INSERT ON slides BEGIN
    INSERT INTO slides_fts(rowid, title, topic, body) VALUES (new.id, new.title, new.topic, new.body);
END;
CREATE TRIGGER IF NOT EXISTS slides_ad AFTER DELETE ON slides BEGIN
    INSERT INTO slides_fts(slides_fts, rowid, title, topic, body) VALUES ('delete', old.id, old.title, old.topic, old.body);
END;
CREATE TRIGGER IF NOT EXISTS slides_au AFTER UPDATE OF title, topic, body ON slides BEGIN
    INSERT INTO slides_fts(slides_fts, rowid, title, topic, body) VALUES ('delete', old.id, old.title, old.topic, old.body);
    INSERT INTO slides_fts(rowid, title, topic, body) VALUES (new.id, new.title, new.topic, new.body);
END;

CREATE TABLE IF NOT EXISTS coursework (
    id           TEXT PRIMARY KEY,
    course_id    TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT,
    keywords     TEXT NOT NULL DEFAULT '[]',   -- JSON list of phrases
    due_at       TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_coursework_course ON coursework(course_id);

CREATE TABLE IF NOT EXISTS gaps (
    id             TEXT PRIMARY KEY,
    student_id     TEXT NOT NULL,
    course_id      TEXT NOT NULL,
    concept        TEXT NOT NULL,
    concept_key    TEXT NOT NULL,              -- lower-cased, trimmed concept for matching
    lecture_id     TEXT,                       -- where it first showed up
    slide_number   INTEGER,
    root_gap_id    TEXT REFERENCES gaps(id) ON DELETE SET NULL,
    status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    attempts       INTEGER NOT NULL DEFAULT 0,
    times_lost     INTEGER NOT NULL DEFAULT 0,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    closed_at      TEXT,
    UNIQUE (student_id, course_id, concept_key)
);
CREATE INDEX IF NOT EXISTS idx_gaps_student ON gaps(student_id, status, last_seen_at);

CREATE TABLE IF NOT EXISTS gap_moments (
    gap_id          TEXT NOT NULL REFERENCES gaps(id) ON DELETE CASCADE,
    lost_moment_id  TEXT NOT NULL REFERENCES lost_moments(id) ON DELETE CASCADE,
    PRIMARY KEY (gap_id, lost_moment_id)
);

CREATE TABLE IF NOT EXISTS coach_sessions (
    id              TEXT PRIMARY KEY,
    student_id      TEXT NOT NULL,
    course_id       TEXT NOT NULL,
    lecture_id      TEXT,
    slide_number    INTEGER,
    lost_moment_id  TEXT REFERENCES lost_moments(id) ON DELETE SET NULL,
    gap_id          TEXT REFERENCES gaps(id) ON DELETE SET NULL,
    question        TEXT,
    mode            TEXT NOT NULL DEFAULT 'guide' CHECK (mode IN ('guide', 'explain', 'locked')),
    locked_by       TEXT REFERENCES coursework(id) ON DELETE SET NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_coach_student ON coach_sessions(student_id, updated_at);

CREATE TABLE IF NOT EXISTS coach_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL REFERENCES coach_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('student', 'coach')),
    content     TEXT NOT NULL,
    mode        TEXT NOT NULL,                 -- the session mode when it was sent
    is_attempt  INTEGER NOT NULL DEFAULT 0,    -- student message that is an honest attempt
    citations   TEXT NOT NULL DEFAULT '[]',    -- JSON [{lecture_id, slide_number}]
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_coach_messages ON coach_messages(session_id, id);

CREATE TABLE IF NOT EXISTS lecture_attendance (
    lecture_id      TEXT NOT NULL,
    student_id      TEXT NOT NULL,
    first_joined_at TEXT NOT NULL,
    PRIMARY KEY (lecture_id, student_id)
);
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
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
