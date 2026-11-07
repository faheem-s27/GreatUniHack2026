"""Hand a stuck student to a human tutor (the brief's bonus, and the
challenge's human-in-the-loop requirement).

The supervisor rule runs in code after every change to a gap:
  * lost on the same idea HANDOFF_AFTER_LOST times (3), or
  * HANDOFF_AFTER_ATTEMPTS honest attempts (6) without closing it
opens a handoff, at most one open handoff per gap. A student can also ask for
a tutor at any time.

Privacy: a tutor sees the idea, the slides it came from, the counts and the
trace back to earlier gaps. The coach conversation is only shared when the
student asked for help themselves and ticked share_transcript.

Routes
  POST  /api/handoffs                          a student asks for a tutor
  GET   /api/handoffs?student_id=...           a student's own handoffs and tutor replies
  GET   /api/courses/{course_id}/handoffs      the tutor queue (open first)
  GET   /api/handoffs/{id}                     one handoff with everything a tutor needs
  PATCH /api/handoffs/{id}                     tutor claims or resolves it, with a note
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from db import connect
from events import log_event

router = APIRouter(prefix="/api", tags=["tutor handoff"])

HANDOFF_AFTER_LOST = 3
HANDOFF_AFTER_ATTEMPTS = 6


class HandoffIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    course_id: str = Field(min_length=1, max_length=64)
    gap_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)
    share_transcript: bool = False


class HandoffPatch(BaseModel):
    status: Literal["claimed", "resolved"]
    tutor: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=5000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def handoff_dict(row) -> dict:
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "gap_id": row["gap_id"],
        "session_id": row["session_id"],
        "reason": row["reason"],
        "student_note": row["student_note"],
        "share_transcript": bool(row["share_transcript"]),
        "status": row["status"],
        "tutor": row["tutor"],
        "tutor_note": row["tutor_note"],
        "created_at": row["created_at"],
        "claimed_at": row["claimed_at"],
        "resolved_at": row["resolved_at"],
    }


def _open_for_gap(conn, gap_id: str):
    return conn.execute(
        "SELECT * FROM handoffs WHERE gap_id = ? AND status IN ('open', 'claimed') ORDER BY created_at DESC LIMIT 1",
        (gap_id,),
    ).fetchone()


def _create(conn, student_id, course_id, reason, gap_id=None, session_id=None, note=None, share=False) -> dict:
    handoff_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO handoffs (id, student_id, course_id, gap_id, session_id, reason, student_note, share_transcript, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (handoff_id, student_id, course_id, gap_id, session_id, reason, note, int(share), _now()),
    )
    log_event(conn, "handoff_requested", student_id, course_id, ref_id=handoff_id, reason=reason, gap_id=gap_id)
    return handoff_dict(conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone())


def supervise(conn, gap_id: str, session_id: str | None = None) -> dict | None:
    """Open a handoff if the student is stuck on this gap. Returns the new handoff, or None."""
    gap = conn.execute("SELECT * FROM gaps WHERE id = ?", (gap_id,)).fetchone()
    if gap is None or gap["status"] != "open" or _open_for_gap(conn, gap_id) is not None:
        return None
    if gap["times_lost"] >= HANDOFF_AFTER_LOST:
        reason = "repeatedly_lost"
    elif gap["attempts"] >= HANDOFF_AFTER_ATTEMPTS:
        reason = "many_attempts"
    else:
        return None
    return _create(conn, gap["student_id"], gap["course_id"], reason, gap_id, session_id)


@router.post("/handoffs", status_code=201)
def request_handoff(body: HandoffIn):
    with connect() as conn:
        if body.gap_id:
            gap = conn.execute("SELECT student_id FROM gaps WHERE id = ?", (body.gap_id,)).fetchone()
            if gap is None or gap["student_id"] != body.student_id:
                raise HTTPException(404, "Gap not found")
            existing = _open_for_gap(conn, body.gap_id)
            if existing is not None:
                return handoff_dict(existing)
        if body.session_id:
            session = conn.execute("SELECT student_id FROM coach_sessions WHERE id = ?", (body.session_id,)).fetchone()
            if session is None or session["student_id"] != body.student_id:
                raise HTTPException(404, "Coach session not found")
        return _create(conn, body.student_id, body.course_id, "student_request", body.gap_id, body.session_id,
                       body.note, body.share_transcript)


@router.get("/handoffs")
def my_handoffs(student_id: str = Query(min_length=1, max_length=64)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM handoffs WHERE student_id = ? ORDER BY created_at DESC", (student_id,)).fetchall()
    return [handoff_dict(r) for r in rows]


@router.get("/courses/{course_id}/handoffs")
def tutor_queue(course_id: str, status: Literal["open", "claimed", "resolved"] | None = None):
    sql = "SELECT * FROM handoffs WHERE course_id = ?"
    params: list = [course_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    with connect() as conn:
        rows = conn.execute(
            sql + " ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'claimed' THEN 1 ELSE 2 END, created_at", params
        ).fetchall()
        return [_with_context(conn, r) for r in rows]


def _with_context(conn, row) -> dict:
    out = handoff_dict(row)
    # Pseudonymous until accounts exist; a tutor replies through the app.
    out["student"] = f"student-{row['student_id'][:8]}"
    gap = conn.execute("SELECT * FROM gaps WHERE id = ?", (row["gap_id"],)).fetchone() if row["gap_id"] else None
    out["gap"] = None
    if gap is not None:
        slide = None
        if gap["lecture_id"] and gap["slide_number"]:
            s = conn.execute(
                """SELECT s.title, l.week FROM slides s JOIN lectures l ON l.id = s.lecture_id
                   WHERE s.lecture_id = ? AND s.slide_number = ?""",
                (gap["lecture_id"], gap["slide_number"]),
            ).fetchone()
            slide = {
                "lecture_id": gap["lecture_id"], "slide_number": gap["slide_number"],
                "title": s["title"] if s else None,
                "citation": f"Week {s['week']}, slide {gap['slide_number']}" if s and s["week"] is not None else None,
            }
        trace, current = [], gap["root_gap_id"]
        while current and len(trace) < 10:
            root = conn.execute("SELECT id, concept, root_gap_id FROM gaps WHERE id = ?", (current,)).fetchone()
            if root is None:
                break
            trace.append(root["concept"])
            current = root["root_gap_id"]
        out["gap"] = {
            "concept": gap["concept"], "status": gap["status"], "attempts": gap["attempts"],
            "times_lost": gap["times_lost"], "slide": slide, "trace": trace,
        }
    out["transcript"] = None
    if row["share_transcript"] and row["session_id"]:
        msgs = conn.execute(
            "SELECT role, content, mode, created_at FROM coach_messages WHERE session_id = ? ORDER BY id", (row["session_id"],)
        ).fetchall()
        out["transcript"] = [dict(m) for m in msgs]
    return out


@router.get("/handoffs/{handoff_id}")
def read_handoff(handoff_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Handoff not found")
        return _with_context(conn, row)


@router.patch("/handoffs/{handoff_id}")
def update_handoff(handoff_id: str, body: HandoffPatch):
    now = _now()
    with connect() as conn:
        row = conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Handoff not found")
        if row["status"] == "resolved":
            raise HTTPException(409, "Handoff is already resolved")
        if body.status == "claimed":
            conn.execute(
                "UPDATE handoffs SET status = 'claimed', tutor = ?, tutor_note = COALESCE(?, tutor_note), claimed_at = ? WHERE id = ?",
                (body.tutor, body.note, now, handoff_id),
            )
        else:
            conn.execute(
                """UPDATE handoffs SET status = 'resolved', tutor = ?, tutor_note = COALESCE(?, tutor_note),
                       claimed_at = COALESCE(claimed_at, ?), resolved_at = ? WHERE id = ?""",
                (body.tutor, body.note, now, now, handoff_id),
            )
        log_event(conn, f"handoff_{body.status}", row["student_id"], row["course_id"], ref_id=handoff_id, tutor=body.tutor)
        return handoff_dict(conn.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone())
