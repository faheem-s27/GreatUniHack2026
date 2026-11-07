"""Storage for coach conversations, with the coach's mode decided in code.

This module stores sessions and messages and enforces the mode rules; the
coach itself (prompts, LLM calls, checking replies) lives elsewhere and calls
these routes or functions.

Mode rules (enforced here, whatever the prompt says):
  * guide    default. Ask first, hint, point to a slide.
  * explain  unlocks once the student has made EXPLAIN_AFTER_ATTEMPTS honest
             attempts in the session (student messages sent with is_attempt that
             pass guardrails.is_honest_attempt: "idk" or "?" do not count).
  * locked   the question, or any later student message, matches assessed
             coursework (coursework.check_question). Locked never unlocks.

Resolving a session closes its gap and marks its lost moment understood, which
is the "gap marked as closed" step of the demo loop.

Routes
  POST   /api/coach/sessions                         start a session
  GET    /api/coach/sessions?student_id=...          a student's sessions
  GET    /api/coach/sessions/{id}?student_id=...     a session with its messages
  GET    /api/coach/sessions/{id}/context?student_id=...
                                                     everything the coach needs to answer:
                                                     the slide, matching slides, open gaps, trace
  POST   /api/coach/sessions/{id}/messages           add a student or coach message
  PATCH  /api/coach/sessions/{id}                    resolve / reopen
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from courses import get_slide, search_slides
from coursework import check_question
from db import connect
from events import log_event
from guardrails import is_honest_attempt
from memory import add_attempt, open_gaps, record_gap, set_gap_status, trace

router = APIRouter(prefix="/api/coach", tags=["coach storage"])

EXPLAIN_AFTER_ATTEMPTS = 3


class SessionIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    course_id: str = Field(min_length=1, max_length=64)
    question: str | None = Field(default=None, max_length=10_000)
    lecture_id: str | None = Field(default=None, max_length=64)
    slide_number: int | None = Field(default=None, ge=1, le=10_000)
    lost_moment_id: str | None = Field(default=None, max_length=64)
    concept: str | None = Field(default=None, max_length=200, description="Records or updates the student's gap for this idea")


class Citation(BaseModel):
    lecture_id: str = Field(min_length=1, max_length=64)
    slide_number: int = Field(ge=1, le=10_000)


class MessageIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    role: Literal["student", "coach"]
    content: str = Field(min_length=1, max_length=20_000)
    is_attempt: bool = False
    citations: list[Citation] = Field(default_factory=list, max_length=20)


class SessionPatch(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    status: Literal["active", "resolved"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_dict(row) -> dict:
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "lecture_id": row["lecture_id"],
        "slide_number": row["slide_number"],
        "lost_moment_id": row["lost_moment_id"],
        "gap_id": row["gap_id"],
        "question": row["question"],
        "mode": row["mode"],
        "locked_by": row["locked_by"],
        "attempts": row["attempts"],
        "attempts_to_explain": max(0, EXPLAIN_AFTER_ATTEMPTS - row["attempts"]) if row["mode"] == "guide" else 0,
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _message_dict(row) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "mode": row["mode"],
        "is_attempt": bool(row["is_attempt"]),
        "citations": json.loads(row["citations"]),
        "created_at": row["created_at"],
    }


def _get_owned(conn, session_id: str, student_id: str):
    row = conn.execute("SELECT * FROM coach_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None or row["student_id"] != student_id:
        raise HTTPException(404, "Coach session not found")
    return row


def _session(conn, session_id: str) -> dict:
    return _session_dict(conn.execute("SELECT * FROM coach_sessions WHERE id = ?", (session_id,)).fetchone())


@router.post("/sessions", status_code=201)
def create_session(body: SessionIn):
    now = _now()
    session_id = str(uuid.uuid4())
    with connect() as conn:
        lecture_id, slide_number = body.lecture_id, body.slide_number
        if body.lost_moment_id:
            moment = conn.execute("SELECT * FROM lost_moments WHERE id = ?", (body.lost_moment_id,)).fetchone()
            if moment is None or moment["student_id"] != body.student_id:
                raise HTTPException(404, "Lost moment not found")
            lecture_id = lecture_id or moment["lecture_id"]
            slide_number = slide_number or moment["slide_number"]

        gap_id = None
        if body.concept:
            gap_id = record_gap(
                conn, body.student_id, body.course_id, body.concept, lecture_id, slide_number, body.lost_moment_id
            )["id"]

        mode, locked_by = "guide", None
        if body.question:
            check = check_question(conn, body.course_id, body.question)
            if check["locked"]:
                mode, locked_by = "locked", check["matches"][0]["id"]

        conn.execute(
            """INSERT INTO coach_sessions (id, student_id, course_id, lecture_id, slide_number, lost_moment_id, gap_id,
                                           question, mode, locked_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, body.student_id, body.course_id, lecture_id, slide_number, body.lost_moment_id, gap_id,
             body.question, mode, locked_by, now, now),
        )
        log_event(conn, "coach_session", body.student_id, body.course_id, lecture_id, slide_number,
                  ref_id=session_id, mode=mode, locked_by=locked_by)
        return _session(conn, session_id)


@router.get("/sessions")
def list_sessions(student_id: str = Query(min_length=1, max_length=64), status: Literal["active", "resolved"] | None = None):
    sql = "SELECT * FROM coach_sessions WHERE student_id = ?"
    params: list = [student_id]
    if status:
        sql += " AND status = ?"
        params.append(status)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY updated_at DESC", params).fetchall()
    return [_session_dict(r) for r in rows]


@router.get("/sessions/{session_id}")
def read_session(session_id: str, student_id: str = Query(min_length=1, max_length=64)):
    with connect() as conn:
        row = _get_owned(conn, session_id, student_id)
        messages = conn.execute("SELECT * FROM coach_messages WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
    return {**_session_dict(row), "messages": [_message_dict(m) for m in messages]}


@router.get("/sessions/{session_id}/context")
def session_context(session_id: str, student_id: str = Query(min_length=1, max_length=64)):
    """One call for the coach: the slide the student got lost on, slides matching the
    question, the student's open gaps, and the trace behind this session's gap."""
    with connect() as conn:
        return build_context(conn, _get_owned(conn, session_id, student_id), student_id)


def build_context(conn, row, student_id: str) -> dict:
    """Everything the coach needs to answer in this session."""
    slide = get_slide(conn, row["lecture_id"], row["slide_number"]) if row["lecture_id"] and row["slide_number"] else None
    query = " ".join(filter(None, [row["question"], slide and slide["topic"], slide and slide["title"]]))
    related = search_slides(conn, query, course_id=row["course_id"]) if query else []
    return {
        "session": _session_dict(row),
        "slide": slide,
        "related_slides": related,
        "open_gaps": open_gaps(conn, student_id, row["course_id"]),
        "trace": trace(conn, row["gap_id"]) if row["gap_id"] else [],
    }


@router.post("/sessions/{session_id}/messages", status_code=201)
def add_message(session_id: str, body: MessageIn):
    with connect() as conn:
        return store_message(conn, session_id, body)


def store_message(conn, session_id: str, body: MessageIn) -> dict:
    """Store one message and apply the mode rules. Returns {message, session, handoff}."""
    now = _now()
    row = _get_owned(conn, session_id, body.student_id)
    mode, locked_by, attempts = row["mode"], row["locked_by"], row["attempts"]

    for c in body.citations:
        if conn.execute(
            "SELECT 1 FROM slides WHERE lecture_id = ? AND slide_number = ?", (c.lecture_id, c.slide_number)
        ).fetchone() is None:
            raise HTTPException(422, f"Citation to a slide that does not exist: {c.lecture_id} slide {c.slide_number}")

    handoff, reason, counted = None, None, False
    if body.role == "student":
        if mode != "locked":
            check = check_question(conn, row["course_id"], body.content)
            if check["locked"]:
                mode, locked_by, reason = "locked", check["matches"][0]["id"], "coursework"
        # Only an honest attempt counts: "idk" three times does not unlock explain mode.
        counted = body.is_attempt and is_honest_attempt(body.content)
        if counted:
            attempts += 1
            log_event(conn, "coach_attempt", body.student_id, row["course_id"], ref_id=session_id, attempt=attempts)
            if row["gap_id"]:
                handoff = add_attempt(conn, row["gap_id"], session_id)
        if mode == "guide" and attempts >= EXPLAIN_AFTER_ATTEMPTS:
            mode, reason = "explain", "attempts"
    if mode != row["mode"]:
        log_event(conn, "coach_mode", body.student_id, row["course_id"], ref_id=session_id,
                  **{"from": row["mode"], "to": mode, "reason": reason})

    # A message is stored with the mode in force when the coach must answer it.
    cur = conn.execute(
        """INSERT INTO coach_messages (session_id, role, content, mode, is_attempt, citations, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, body.role, body.content, mode, int(body.role == "student" and counted),
         json.dumps([c.model_dump() for c in body.citations]), now),
    )
    conn.execute(
        "UPDATE coach_sessions SET mode = ?, locked_by = ?, attempts = ?, updated_at = ? WHERE id = ?",
        (mode, locked_by, attempts, now, session_id),
    )
    message = conn.execute("SELECT * FROM coach_messages WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"message": _message_dict(message), "session": _session(conn, session_id), "handoff": handoff}


@router.patch("/sessions/{session_id}")
def update_session(session_id: str, body: SessionPatch):
    now = _now()
    resolved = body.status == "resolved"
    with connect() as conn:
        row = _get_owned(conn, session_id, body.student_id)
        conn.execute("UPDATE coach_sessions SET status = ?, updated_at = ? WHERE id = ?", (body.status, now, session_id))
        if resolved and row["status"] != "resolved":
            log_event(conn, "coach_resolved", body.student_id, row["course_id"], ref_id=session_id,
                      attempts=row["attempts"], mode=row["mode"])
        if row["gap_id"]:
            set_gap_status(conn, row["gap_id"], "closed" if resolved else "open")
        if row["lost_moment_id"]:
            conn.execute(
                "UPDATE lost_moments SET resolved = ?, resolved_at = ? WHERE id = ?",
                (int(resolved), now if resolved else None, row["lost_moment_id"]),
            )
        return _session(conn, session_id)
