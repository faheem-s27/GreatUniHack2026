"""The "I'm lost" button: save the exact slide and time a student got lost.

Routes
  POST   /api/lost-moments                         save a moment (one tap)
  GET    /api/lost-moments?student_id=...          a student's own moments
  PATCH  /api/lost-moments/{id}                    mark understood / reopen
  PUT    /api/lost-moments/{id}/screenshot         attach a photo of the slide
  GET    /api/lost-moments/{id}/screenshot         fetch that photo
  GET    /api/lectures/{lecture_id}/heatmap        anonymised per-slide counts

Privacy rules enforced here, not in the frontend:
  * The heatmap counts distinct students and hides any slide with fewer than
    HEATMAP_MIN_STUDENTS, so a single student cannot be singled out.
  * A student can only read or change their own moments (student_id must match).
"""

import base64
import binascii
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from db import connect

router = APIRouter(prefix="/api", tags=["lost moments"])

HEATMAP_MIN_STUDENTS = 5
# Repeated taps on the same slide within this window count as one moment, so
# a nervous double-tap does not inflate the lecturer's heatmap.
DEDUPE_WINDOW = timedelta(seconds=30)
MAX_SCREENSHOT_BYTES = 3 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class LostMomentIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    lecture_id: str = Field(min_length=1, max_length=64)
    slide_number: int = Field(ge=1, le=10_000)
    topic: str | None = Field(default=None, max_length=200)
    lecture_time_s: int | None = Field(default=None, ge=0, description="Seconds since the lecture started")
    # Client-side id, so a moment queued offline is not saved twice on retry.
    id: str | None = Field(default=None, max_length=64)


class LostMomentPatch(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    resolved: bool


class ScreenshotIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    data_url: str = Field(description="data:image/jpeg;base64,...")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(row) -> dict:
    return {
        "id": row["id"],
        "lecture_id": row["lecture_id"],
        "slide_number": row["slide_number"],
        "topic": row["topic"],
        "lecture_time_s": row["lecture_time_s"],
        "created_at": row["created_at"],
        "resolved": bool(row["resolved"]),
        "resolved_at": row["resolved_at"],
        "has_screenshot": row["screenshot_type"] is not None,
    }


def _get_owned(conn, moment_id: str, student_id: str):
    row = conn.execute("SELECT * FROM lost_moments WHERE id = ?", (moment_id,)).fetchone()
    # Same 404 for "missing" and "not yours", so ids cannot be probed.
    if row is None or row["student_id"] != student_id:
        raise HTTPException(404, "Lost moment not found")
    return row


@router.post("/lost-moments", status_code=201)
def create_lost_moment(body: LostMomentIn, response: Response):
    now = _now()
    with connect() as conn:
        if body.id:
            existing = conn.execute("SELECT * FROM lost_moments WHERE id = ?", (body.id,)).fetchone()
            if existing is not None:
                if existing["student_id"] != body.student_id:
                    raise HTTPException(409, "Id already in use")
                response.status_code = 200
                return _to_dict(existing)

        recent = conn.execute(
            """SELECT * FROM lost_moments
               WHERE student_id = ? AND lecture_id = ? AND slide_number = ? AND created_at >= ?
               ORDER BY created_at DESC LIMIT 1""",
            (body.student_id, body.lecture_id, body.slide_number, (now - DEDUPE_WINDOW).isoformat()),
        ).fetchone()
        if recent is not None:
            response.status_code = 200
            return _to_dict(recent)

        moment_id = body.id or str(uuid.uuid4())
        conn.execute(
            """INSERT INTO lost_moments (id, student_id, lecture_id, slide_number, topic, lecture_time_s, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (moment_id, body.student_id, body.lecture_id, body.slide_number, body.topic, body.lecture_time_s, now.isoformat()),
        )
        row = conn.execute("SELECT * FROM lost_moments WHERE id = ?", (moment_id,)).fetchone()
        return _to_dict(row)


@router.get("/lost-moments")
def list_lost_moments(student_id: str = Query(min_length=1, max_length=64), lecture_id: str | None = None):
    query = "SELECT * FROM lost_moments WHERE student_id = ?"
    params: list = [student_id]
    if lecture_id:
        query += " AND lecture_id = ?"
        params.append(lecture_id)
    with connect() as conn:
        rows = conn.execute(query + " ORDER BY created_at DESC", params).fetchall()
    return [_to_dict(r) for r in rows]


@router.patch("/lost-moments/{moment_id}")
def update_lost_moment(moment_id: str, body: LostMomentPatch):
    with connect() as conn:
        _get_owned(conn, moment_id, body.student_id)
        conn.execute(
            "UPDATE lost_moments SET resolved = ?, resolved_at = ? WHERE id = ?",
            (int(body.resolved), _now().isoformat() if body.resolved else None, moment_id),
        )
        return _to_dict(conn.execute("SELECT * FROM lost_moments WHERE id = ?", (moment_id,)).fetchone())


@router.put("/lost-moments/{moment_id}/screenshot")
def attach_screenshot(moment_id: str, body: ScreenshotIn):
    header, sep, encoded = body.data_url.partition(",")
    mime = header.removeprefix("data:").removesuffix(";base64")
    if not sep or not header.endswith(";base64") or mime not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(422, "Expected a base64 JPEG, PNG or WebP data URL")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Screenshot is not valid base64")
    if len(data) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(413, "Screenshot is larger than 3 MB")

    with connect() as conn:
        _get_owned(conn, moment_id, body.student_id)
        conn.execute("UPDATE lost_moments SET screenshot = ?, screenshot_type = ? WHERE id = ?", (data, mime, moment_id))
        return _to_dict(conn.execute("SELECT * FROM lost_moments WHERE id = ?", (moment_id,)).fetchone())


@router.get("/lost-moments/{moment_id}/screenshot")
def get_screenshot(moment_id: str, student_id: str = Query(min_length=1, max_length=64)):
    with connect() as conn:
        row = _get_owned(conn, moment_id, student_id)
    if row["screenshot"] is None:
        raise HTTPException(404, "No screenshot for this moment")
    return Response(content=row["screenshot"], media_type=row["screenshot_type"], headers={"Cache-Control": "private, max-age=3600"})


@router.get("/lectures/{lecture_id}/heatmap")
def lecture_heatmap(lecture_id: str):
    """Distinct students lost per slide. Slides under the threshold are hidden."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT slide_number, COUNT(DISTINCT student_id) AS students
               FROM lost_moments WHERE lecture_id = ?
               GROUP BY slide_number ORDER BY slide_number""",
            (lecture_id,),
        ).fetchall()
    slides = [
        {
            "slide_number": r["slide_number"],
            "students": r["students"] if r["students"] >= HEATMAP_MIN_STUDENTS else None,
            "hidden": r["students"] < HEATMAP_MIN_STUDENTS,
        }
        for r in rows
    ]
    return {"lecture_id": lecture_id, "min_students": HEATMAP_MIN_STUDENTS, "slides": slides}
