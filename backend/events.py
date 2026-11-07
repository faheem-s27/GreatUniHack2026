"""Event log: every step a student or the system takes, one row each.

The challenge asks to "record every step": the log is the debugging tool,
the testing evidence, and the source of the brief's success metrics
(insights.py). Events are written in the same transaction as the change they
describe, so the log never disagrees with the data.

Kinds
  lost_tap            a new lost moment (not a deduplicated double tap)
  gap_recorded        a gap was created, or seen again
  gap_closed / gap_reopened
  coach_session       a coach session started (detail: mode)
  coach_attempt       an honest attempt in a session
  coach_mode          the mode changed (detail: from, to, reason)
  coach_resolved      the student worked it out
  handoff_requested / handoff_claimed / handoff_resolved
  slide_recapped      a lecturer marked a slide as recapped

Routes
  GET /api/events?student_id=...    a student's own timeline (newest first)
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from db import connect

router = APIRouter(prefix="/api", tags=["event log"])


def log_event(
    conn,
    kind: str,
    student_id: str | None = None,
    course_id: str | None = None,
    lecture_id: str | None = None,
    slide_number: int | None = None,
    ref_id: str | None = None,
    **detail,
) -> None:
    conn.execute(
        """INSERT INTO events (at, kind, student_id, course_id, lecture_id, slide_number, ref_id, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now(timezone.utc).isoformat(), kind, student_id, course_id, lecture_id, slide_number, ref_id,
         json.dumps(detail, default=str)),
    )


def _event_dict(row) -> dict:
    return {
        "id": row["id"],
        "at": row["at"],
        "kind": row["kind"],
        "course_id": row["course_id"],
        "lecture_id": row["lecture_id"],
        "slide_number": row["slide_number"],
        "ref_id": row["ref_id"],
        "detail": json.loads(row["detail"]),
    }


@router.get("/events")
def student_events(student_id: str = Query(min_length=1, max_length=64), kind: str | None = None, limit: int = Query(100, ge=1, le=500)):
    sql = "SELECT * FROM events WHERE student_id = ?"
    params: list = [student_id]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
    return [_event_dict(r) for r in rows]
