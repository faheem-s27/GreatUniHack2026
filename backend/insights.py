"""Lecturer insights across a whole course, and the brief's success metrics.

Routes
  GET /api/courses/{course_id}/insights   per-lecture heatmap summary, the slides that lost the
                                          most students across the course, and the concepts most
                                          students have open gaps on
  GET /api/courses/{course_id}/metrics    "How we know it works" numbers from the brief
  POST /api/lectures/{lecture_id}/slides/{n}/recap   the lecturer recapped a slide (a metric)

Same privacy rule as the heatmap: anything counted per slide or per concept is
only shown once HEATMAP_MIN_STUDENTS or more distinct students are in it.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import connect
from events import log_event
from lost_moments import HEATMAP_MIN_STUDENTS, heatmap_for

router = APIRouter(prefix="/api", tags=["lecturer insights"])


def _course_or_404(conn, course_id: str):
    course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if course is None:
        raise HTTPException(404, "Course not found")
    return course


@router.get("/courses/{course_id}/insights")
def course_insights(course_id: str, top: int = 5):
    top = max(1, min(top, 20))
    with connect() as conn:
        course = _course_or_404(conn, course_id)
        lectures = conn.execute(
            "SELECT * FROM lectures WHERE course_id = ? ORDER BY week, held_at, title", (course_id,)
        ).fetchall()

        per_lecture, hot_slides = [], []
        for lecture in lectures:
            heat = heatmap_for(conn, lecture["id"])
            lost_students = conn.execute(
                "SELECT COUNT(DISTINCT student_id) FROM lost_moments WHERE lecture_id = ?", (lecture["id"],)
            ).fetchone()[0]
            visible = [s for s in heat["slides"] if not s["hidden"]]
            per_lecture.append({
                "lecture_id": lecture["id"],
                "week": lecture["week"],
                "title": lecture["title"],
                "attendance": heat["attendance"],
                "students_lost": lost_students if lost_students >= HEATMAP_MIN_STUDENTS else None,
                "most_lost_slide": heat["most_lost_slide"],
            })
            hot_slides += [
                {"lecture_id": lecture["id"], "week": lecture["week"], **s, "citation": f"Week {lecture['week']}, slide {s['slide_number']}"}
                for s in visible
            ]
        hot_slides.sort(key=lambda s: s["students"], reverse=True)

        concepts = conn.execute(
            """SELECT MIN(concept) AS concept, COUNT(DISTINCT student_id) AS students,
                      SUM(status = 'open') AS still_open
               FROM gaps WHERE course_id = ?
               GROUP BY concept_key HAVING COUNT(DISTINCT student_id) >= ?
               ORDER BY students DESC LIMIT ?""",
            (course_id, HEATMAP_MIN_STUDENTS, top),
        ).fetchall()

    return {
        "course_id": course["id"],
        "title": course["title"],
        "min_students": HEATMAP_MIN_STUDENTS,
        "lectures": per_lecture,
        "most_lost_slides": hot_slides[:top],
        "struggling_concepts": [dict(c) for c in concepts],
    }


class RecapIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.post("/lectures/{lecture_id}/slides/{slide_number}/recap", status_code=201)
def mark_recapped(lecture_id: str, slide_number: int, body: RecapIn | None = None):
    """The lecturer acted on the heatmap: they recapped or changed this slide."""
    with connect() as conn:
        lecture = conn.execute("SELECT course_id FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        if lecture is None:
            raise HTTPException(404, "Lecture not found")
        log_event(conn, "slide_recapped", course_id=lecture["course_id"], lecture_id=lecture_id,
                  slide_number=slide_number, note=body.note if body else None)
    return {"lecture_id": lecture_id, "slide_number": slide_number, "recapped": True}


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


@router.get("/courses/{course_id}/metrics")
def course_metrics(course_id: str):
    """The brief's "How we know it works", computed from the data and the event log.

    repeat_lost_rate        share of gaps a student got lost on more than once (lower is better)
    repeat_lost_by_week     the same, week by week, so the trend over the term is visible
    closed_then_reopened    gaps closed by coaching that came back (coaching that did not stick)
    coach.*                 sessions, how many the student resolved, attempts it took, mode changes
    handoffs.*              students handed to a human tutor, by reason
    lecturer_actions        slides the lecturer recapped after seeing the heatmap
    """
    with connect() as conn:
        _course_or_404(conn, course_id)
        one = lambda sql, *p: conn.execute(sql, (course_id, *p)).fetchone()[0]  # noqa: E731

        lost_total = one("SELECT COUNT(*) FROM lost_moments m JOIN lectures l ON l.id = m.lecture_id WHERE l.course_id = ?")
        lost_students = one("SELECT COUNT(DISTINCT m.student_id) FROM lost_moments m JOIN lectures l ON l.id = m.lecture_id WHERE l.course_id = ?")
        gaps_total = one("SELECT COUNT(*) FROM gaps WHERE course_id = ?")
        gaps_closed = one("SELECT COUNT(*) FROM gaps WHERE course_id = ? AND status = 'closed'")
        gaps_lost = one("SELECT COUNT(*) FROM gaps WHERE course_id = ? AND times_lost >= 1")
        gaps_repeat = one("SELECT COUNT(*) FROM gaps WHERE course_id = ? AND times_lost >= 2")
        reopened = one(
            """SELECT COUNT(DISTINCT r.ref_id) FROM events r JOIN events c
                 ON c.ref_id = r.ref_id AND c.kind = 'gap_closed' AND c.id < r.id
               WHERE r.kind = 'gap_reopened' AND r.course_id = ?"""
        )
        weekly = conn.execute(
            """SELECT strftime('%Y-W%W', at) AS week,
                      SUM(json_extract(detail, '$.new') = 0) AS repeat,
                      SUM(json_extract(detail, '$.new') = 1) AS first_time
               FROM events
               WHERE course_id = ? AND kind IN ('gap_recorded', 'gap_reopened')
                 AND json_extract(detail, '$.lost_moment_id') IS NOT NULL
               GROUP BY week ORDER BY week""",
            (course_id,),
        ).fetchall()

        sessions = one("SELECT COUNT(*) FROM coach_sessions WHERE course_id = ?")
        resolved = one("SELECT COUNT(*) FROM coach_sessions WHERE course_id = ? AND status = 'resolved'")
        avg_attempts = conn.execute(
            "SELECT AVG(attempts) FROM coach_sessions WHERE course_id = ? AND status = 'resolved'", (course_id,)
        ).fetchone()[0]
        explain = one("SELECT COUNT(DISTINCT ref_id) FROM events WHERE course_id = ? AND kind = 'coach_mode' AND json_extract(detail, '$.to') = 'explain'")
        locked = one("SELECT COUNT(*) FROM coach_sessions WHERE course_id = ? AND mode = 'locked'")

        handoffs = {r["reason"]: r["n"] for r in conn.execute(
            "SELECT reason, COUNT(*) AS n FROM handoffs WHERE course_id = ? GROUP BY reason", (course_id,)
        )}
        handoffs_resolved = one("SELECT COUNT(*) FROM handoffs WHERE course_id = ? AND status = 'resolved'")
        recaps = conn.execute(
            """SELECT lecture_id, slide_number, MAX(at) AS at FROM events
               WHERE course_id = ? AND kind = 'slide_recapped' GROUP BY lecture_id, slide_number ORDER BY at""",
            (course_id,),
        ).fetchall()

    return {
        "course_id": course_id,
        "lost_moments": {"total": lost_total, "students": lost_students},
        "gaps": {
            "total": gaps_total,
            "closed": gaps_closed,
            "closure_rate": _rate(gaps_closed, gaps_total),
            "repeat_lost_rate": _rate(gaps_repeat, gaps_lost),
            "closed_then_reopened": reopened,
        },
        "repeat_lost_by_week": [
            {"week": w["week"], "repeat": w["repeat"] or 0, "first_time": w["first_time"] or 0,
             "repeat_rate": _rate(w["repeat"] or 0, (w["repeat"] or 0) + (w["first_time"] or 0))}
            for w in weekly
        ],
        "coach": {
            "sessions": sessions,
            "resolved": resolved,
            "resolution_rate": _rate(resolved, sessions),
            "avg_attempts_to_resolve": round(avg_attempts, 2) if avg_attempts is not None else None,
            "explain_unlocked": explain,
            "locked_by_coursework": locked,
        },
        "handoffs": {"total": sum(handoffs.values()), "resolved": handoffs_resolved, "by_reason": handoffs},
        "lecturer_actions": {"slides_recapped": len(recaps), "recaps": [dict(r) for r in recaps]},
    }
