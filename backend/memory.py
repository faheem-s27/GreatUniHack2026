"""Student memory: the ideas each student keeps struggling with ("gaps").

A gap is one concept for one student in one course, e.g. "partial derivatives".
Recording the same concept again (same words, any case) updates the existing
gap instead of making a new one, and reopens it if it had been closed. A gap
can point to a root gap from an earlier week, so a week 6 problem can be
traced back to a week 2 gap.

Routes
  POST   /api/gaps                       record a gap (or update the existing one)
  GET    /api/gaps?student_id=...        a student's gaps, open first
  GET    /api/gaps/{id}?student_id=...   one gap, its lost moments and its trace back
  PATCH  /api/gaps/{id}                  close / reopen, or set its root gap

As with lost moments there are no accounts yet, so student_id must match on
every read and change, and "not yours" looks the same as "not found".
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db import connect
from events import log_event
from handoffs import supervise

router = APIRouter(prefix="/api", tags=["student memory"])

MAX_TRACE = 10


class GapIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    course_id: str = Field(min_length=1, max_length=64)
    concept: str = Field(min_length=1, max_length=200)
    lecture_id: str | None = Field(default=None, max_length=64)
    slide_number: int | None = Field(default=None, ge=1, le=10_000)
    lost_moment_id: str | None = Field(default=None, max_length=64)
    root_gap_id: str | None = Field(default=None, max_length=64)


class GapPatch(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    status: Literal["open", "closed"] | None = None
    root_gap_id: str | None = Field(default=None, max_length=64)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def concept_key(concept: str) -> str:
    return " ".join(concept.lower().split())


def gap_dict(row) -> dict:
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "concept": row["concept"],
        "lecture_id": row["lecture_id"],
        "slide_number": row["slide_number"],
        "root_gap_id": row["root_gap_id"],
        "status": row["status"],
        "attempts": row["attempts"],
        "times_lost": row["times_lost"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "closed_at": row["closed_at"],
    }


def get_owned_gap(conn, gap_id: str, student_id: str):
    row = conn.execute("SELECT * FROM gaps WHERE id = ?", (gap_id,)).fetchone()
    if row is None or row["student_id"] != student_id:
        raise HTTPException(404, "Gap not found")
    return row


def _check_root(conn, gap_id: str | None, root_gap_id: str, student_id: str) -> None:
    get_owned_gap(conn, root_gap_id, student_id)
    # Walk up from the proposed root; reaching gap_id again would make a loop.
    current, seen = root_gap_id, 0
    while current and seen <= MAX_TRACE:
        if current == gap_id:
            raise HTTPException(422, "Root gap would create a loop")
        row = conn.execute("SELECT root_gap_id FROM gaps WHERE id = ?", (current,)).fetchone()
        current, seen = (row["root_gap_id"] if row else None), seen + 1


def record_gap(
    conn,
    student_id: str,
    course_id: str,
    concept: str,
    lecture_id: str | None = None,
    slide_number: int | None = None,
    lost_moment_id: str | None = None,
    root_gap_id: str | None = None,
) -> dict:
    """Create the gap or update the existing one for this concept. Returns the gap."""
    key = concept_key(concept)
    now = _now()
    existing = conn.execute(
        "SELECT * FROM gaps WHERE student_id = ? AND course_id = ? AND concept_key = ?", (student_id, course_id, key)
    ).fetchone()
    gap_id = existing["id"] if existing else str(uuid.uuid4())
    if root_gap_id:
        _check_root(conn, gap_id, root_gap_id, student_id)
    if lost_moment_id:
        moment = conn.execute("SELECT student_id FROM lost_moments WHERE id = ?", (lost_moment_id,)).fetchone()
        if moment is None or moment["student_id"] != student_id:
            raise HTTPException(404, "Lost moment not found")

    if existing is None:
        conn.execute(
            """INSERT INTO gaps (id, student_id, course_id, concept, concept_key, lecture_id, slide_number,
                                 root_gap_id, first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gap_id, student_id, course_id, concept.strip(), key, lecture_id, slide_number, root_gap_id, now, now),
        )
    else:
        conn.execute(
            """UPDATE gaps SET last_seen_at = ?, status = 'open', closed_at = NULL,
                   root_gap_id = COALESCE(?, root_gap_id),
                   lecture_id = COALESCE(lecture_id, ?), slide_number = COALESCE(slide_number, ?)
               WHERE id = ?""",
            (now, root_gap_id, lecture_id, slide_number, gap_id),
        )
    if lost_moment_id:
        linked = conn.execute(
            "INSERT OR IGNORE INTO gap_moments (gap_id, lost_moment_id) VALUES (?, ?)", (gap_id, lost_moment_id)
        ).rowcount
        if linked:
            conn.execute("UPDATE gaps SET times_lost = times_lost + 1 WHERE id = ?", (gap_id,))
    reopened = existing is not None and existing["status"] == "closed"
    log_event(conn, "gap_reopened" if reopened else "gap_recorded", student_id, course_id, lecture_id, slide_number,
              ref_id=gap_id, concept=concept.strip(), new=existing is None, lost_moment_id=lost_moment_id)
    handoff = supervise(conn, gap_id)
    return gap_dict(conn.execute("SELECT * FROM gaps WHERE id = ?", (gap_id,)).fetchone()) | {"handoff": handoff}


def add_attempt(conn, gap_id: str, session_id: str | None = None) -> dict | None:
    """Count an honest attempt. Returns a new tutor handoff if the student is now stuck."""
    conn.execute("UPDATE gaps SET attempts = attempts + 1, last_seen_at = ? WHERE id = ?", (_now(), gap_id))
    return supervise(conn, gap_id, session_id)


def set_gap_status(conn, gap_id: str, status: str) -> None:
    row = conn.execute("SELECT student_id, course_id, status FROM gaps WHERE id = ?", (gap_id,)).fetchone()
    conn.execute(
        "UPDATE gaps SET status = ?, closed_at = ? WHERE id = ?",
        (status, _now() if status == "closed" else None, gap_id),
    )
    if row is not None and row["status"] != status:
        log_event(conn, "gap_closed" if status == "closed" else "gap_reopened", row["student_id"], row["course_id"], ref_id=gap_id)


def trace(conn, gap_id: str) -> list[dict]:
    """The chain of root gaps behind this one, nearest first (excluding the gap itself)."""
    chain, row = [], conn.execute("SELECT root_gap_id FROM gaps WHERE id = ?", (gap_id,)).fetchone()
    current = row["root_gap_id"] if row else None
    while current and len(chain) < MAX_TRACE:
        root = conn.execute("SELECT * FROM gaps WHERE id = ?", (current,)).fetchone()
        if root is None:
            break
        chain.append(gap_dict(root))
        current = root["root_gap_id"]
    return chain


def open_gaps(conn, student_id: str, course_id: str | None = None, limit: int = 20) -> list[dict]:
    """What this student currently struggles with, most recent first. For the coach's context."""
    sql = "SELECT * FROM gaps WHERE student_id = ? AND status = 'open'"
    params: list = [student_id]
    if course_id:
        sql += " AND course_id = ?"
        params.append(course_id)
    rows = conn.execute(sql + " ORDER BY last_seen_at DESC LIMIT ?", (*params, limit)).fetchall()
    return [gap_dict(r) for r in rows]


@router.post("/gaps", status_code=201)
def create_gap(body: GapIn):
    with connect() as conn:
        return record_gap(
            conn, body.student_id, body.course_id, body.concept,
            body.lecture_id, body.slide_number, body.lost_moment_id, body.root_gap_id,
        )


@router.get("/gaps")
def list_gaps(
    student_id: str = Query(min_length=1, max_length=64),
    course_id: str | None = None,
    status: Literal["open", "closed"] | None = None,
):
    sql = "SELECT * FROM gaps WHERE student_id = ?"
    params: list = [student_id]
    if course_id:
        sql += " AND course_id = ?"
        params.append(course_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY status = 'closed', last_seen_at DESC", params).fetchall()
    return [gap_dict(r) for r in rows]


@router.get("/gaps/{gap_id}")
def read_gap(gap_id: str, student_id: str = Query(min_length=1, max_length=64)):
    with connect() as conn:
        row = get_owned_gap(conn, gap_id, student_id)
        moments = conn.execute(
            """SELECT m.id, m.lecture_id, m.slide_number, m.topic, m.created_at, m.resolved
               FROM gap_moments gm JOIN lost_moments m ON m.id = gm.lost_moment_id
               WHERE gm.gap_id = ? ORDER BY m.created_at""",
            (gap_id,),
        ).fetchall()
        return {
            **gap_dict(row),
            "lost_moments": [dict(m) | {"resolved": bool(m["resolved"])} for m in moments],
            "trace": trace(conn, gap_id),
        }


@router.patch("/gaps/{gap_id}")
def update_gap(gap_id: str, body: GapPatch):
    with connect() as conn:
        get_owned_gap(conn, gap_id, body.student_id)
        if body.root_gap_id is not None:
            _check_root(conn, gap_id, body.root_gap_id, body.student_id)
            conn.execute("UPDATE gaps SET root_gap_id = ? WHERE id = ?", (body.root_gap_id, gap_id))
        if body.status is not None:
            set_gap_status(conn, gap_id, body.status)
        return gap_dict(conn.execute("SELECT * FROM gaps WHERE id = ?", (gap_id,)).fetchone())
