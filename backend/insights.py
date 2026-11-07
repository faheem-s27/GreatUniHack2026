"""Lecturer insights across a whole course, and the brief's success metrics.

Routes
  GET /api/courses/{course_id}/insights   per-lecture heatmap summary, the slides that lost the
                                          most students across the course, and the concepts most
                                          students have open gaps on
  GET /api/courses/{course_id}/metrics    "How we know it works" numbers from the brief

Same privacy rule as the heatmap: anything counted per slide or per concept is
only shown once HEATMAP_MIN_STUDENTS or more distinct students are in it.
"""

from fastapi import APIRouter, HTTPException

from db import connect
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
