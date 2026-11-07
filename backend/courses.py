"""Courses, lectures and slides, plus slide search with slide-number citations.

Routes
  GET    /api/courses                                  all courses
  POST   /api/courses                                  create or update a course
  GET    /api/courses/{course_id}                      a course with its lectures
  POST   /api/courses/{course_id}/lectures             create or update a lecture
  GET    /api/lectures/{lecture_id}                    a lecture with its slides (text only)
  PUT    /api/lectures/{lecture_id}/slides             replace all slides of a lecture (ingest)
  GET    /api/lectures/{lecture_id}/slides/{n}         one slide
  PUT    /api/lectures/{lecture_id}/slides/{n}/image   attach a slide image (base64 data URL)
  GET    /api/lectures/{lecture_id}/slides/{n}/image   fetch that image
  GET    /api/search?q=...&course_id=...               slide search, best match first

The search uses SQLite FTS5 so it works with no extra services. When Chroma is
added, only search_slides() needs to change; the response shape can stay.
"""

import base64
import binascii
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from accounts import require_staff
import search_index
from db import connect

router = APIRouter(prefix="/api", tags=["courses and slides"])

ID = r"^[A-Za-z0-9_.-]+$"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CourseIn(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=ID)
    title: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=32)
    term: str | None = Field(default=None, max_length=64)


class LectureIn(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=ID)
    title: str = Field(min_length=1, max_length=200)
    week: int | None = Field(default=None, ge=0, le=60)
    held_at: str | None = Field(default=None, max_length=40, description="ISO date or datetime")


class SlideIn(BaseModel):
    slide_number: int = Field(ge=1, le=10_000)
    title: str | None = Field(default=None, max_length=300)
    topic: str | None = Field(default=None, max_length=200)
    body: str = Field(default="", max_length=20_000)


class SlidesIn(BaseModel):
    slides: list[SlideIn] = Field(max_length=1000)


class ImageIn(BaseModel):
    data_url: str = Field(description="data:image/png;base64,...")


def citation(week: int | None, slide_number: int) -> str:
    return f"Week {week}, slide {slide_number}" if week is not None else f"Slide {slide_number}"


def _slide_dict(row, week: int | None = None) -> dict:
    return {
        "lecture_id": row["lecture_id"],
        "slide_number": row["slide_number"],
        "title": row["title"],
        "topic": row["topic"],
        "body": row["body"],
        "has_image": row["image_type"] is not None,
        "citation": citation(week, row["slide_number"]),
    }


def get_lecture_row(conn, lecture_id: str):
    row = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Lecture not found")
    return row


def get_slide(conn, lecture_id: str, slide_number: int) -> dict | None:
    """Slide text for the coach: {lecture_id, slide_number, title, topic, body, citation} or None."""
    row = conn.execute(
        """SELECT s.*, l.week FROM slides s JOIN lectures l ON l.id = s.lecture_id
           WHERE s.lecture_id = ? AND s.slide_number = ?""",
        (lecture_id, slide_number),
    ).fetchone()
    return _slide_dict(row, row["week"]) if row else None


# Question and filler words. Without this, "how does resolution work" ranks
# slides about "hard work" above the ones about resolution.
STOPWORDS = set("""
a about above after again all also am an and any are as at be because been before being below between both but by
can could did do does doing done down during each few for from further get gets got had has have having he her here
hers him his how i if in into is it its just let me mean means meaning more most my no nor not now of off on once
only or other our out over own please really same she should so some such than that the their them then there these
they this those through to too under until up very was we were what when where which while who whom why will with
work works would you your explain understand understanding confused lost help tell show give example examples
""".split())


def _variants(word: str) -> list[str]:
    # British and American spellings: normalisation / normalization, analyse / analyze.
    out = [word]
    for a, b in (("isation", "ization"), ("ise", "ize"), ("ising", "izing"), ("yse", "yze"), ("our", "or")):
        if word.endswith(a):
            out.append(word[: -len(a)] + b)
        elif word.endswith(b):
            out.append(word[: -len(b)] + a)
    return out


def _fts_query(text: str) -> str | None:
    # Quote every word so user text can never be read as FTS syntax; OR them so
    # a slide matching some of the words still ranks. Filler words are dropped
    # unless nothing else is left.
    words = re.findall(r"\w+", text.lower())[:30]
    content = [w for w in words if w not in STOPWORDS and len(w) > 1] or words
    terms = dict.fromkeys(v for w in content[:20] for v in _variants(w))
    return " OR ".join(f'"{t}"' for t in terms) if terms else None


def search_slides(conn, q: str, course_id: str | None = None, lecture_id: str | None = None, limit: int = 5) -> list[dict]:
    """Best-matching slides for a question. Used by the coach to cite slides.

    Keyword search always runs. With semantic search on (search_index.py) its
    results are merged in; each result says how it matched: keyword, meaning or both.
    """
    keyword = _keyword_search(conn, q, course_id, lecture_id, limit * 3 if search_index.enabled() else limit)
    if not search_index.enabled():
        return [r | {"match": "keyword"} for r in keyword[:limit]]
    semantic = search_index.semantic_hits(q, course_id, lecture_id, limit * 3)
    by_key = {(r["lecture_id"], r["slide_number"]): r for r in keyword}
    out = []
    for key, how in search_index.fuse(list(by_key), semantic, limit):
        hit = by_key.get(key) or _hit_without_snippet(conn, *key)
        if hit:
            out.append(hit | {"match": how})
    return out


def _hit_without_snippet(conn, lecture_id: str, slide_number: int) -> dict | None:
    r = conn.execute(
        """SELECT s.lecture_id, s.slide_number, s.title, s.topic, s.body, l.week, l.title AS lecture_title, l.course_id
           FROM slides s JOIN lectures l ON l.id = s.lecture_id WHERE s.lecture_id = ? AND s.slide_number = ?""",
        (lecture_id, slide_number),
    ).fetchone()
    if r is None:
        return None
    body = " ".join((r["body"] or "").split())
    return {
        "course_id": r["course_id"], "lecture_id": r["lecture_id"], "lecture_title": r["lecture_title"],
        "week": r["week"], "slide_number": r["slide_number"], "title": r["title"], "topic": r["topic"],
        "snippet": body[:160] + ("…" if len(body) > 160 else ""), "citation": citation(r["week"], r["slide_number"]),
    }


def _keyword_search(conn, q: str, course_id: str | None, lecture_id: str | None, limit: int) -> list[dict]:
    match = _fts_query(q)
    if match is None:
        return []
    sql = """SELECT s.lecture_id, s.slide_number, s.title, s.topic, l.week, l.title AS lecture_title, l.course_id,
                    snippet(slides_fts, 2, '[', ']', '…', 12) AS snippet,
                    bm25(slides_fts, 5.0, 3.0, 1.0) AS score
             FROM slides_fts
             JOIN slides s ON s.id = slides_fts.rowid
             JOIN lectures l ON l.id = s.lecture_id
             WHERE slides_fts MATCH ?"""
    params: list = [match]
    if course_id:
        sql += " AND l.course_id = ?"
        params.append(course_id)
    if lecture_id:
        sql += " AND s.lecture_id = ?"
        params.append(lecture_id)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)
    return [
        {
            "course_id": r["course_id"],
            "lecture_id": r["lecture_id"],
            "lecture_title": r["lecture_title"],
            "week": r["week"],
            "slide_number": r["slide_number"],
            "title": r["title"],
            "topic": r["topic"],
            "snippet": r["snippet"],
            "citation": citation(r["week"], r["slide_number"]),
        }
        for r in conn.execute(sql, params).fetchall()
    ]


@router.get("/courses")
def list_courses():
    with connect() as conn:
        rows = conn.execute(
            """SELECT c.*, COUNT(l.id) AS lecture_count FROM courses c
               LEFT JOIN lectures l ON l.course_id = c.id GROUP BY c.id ORDER BY c.title"""
        ).fetchall()
    return [{"id": r["id"], "code": r["code"], "title": r["title"], "term": r["term"], "lecture_count": r["lecture_count"]} for r in rows]


@router.post("/courses", status_code=201, dependencies=[Depends(require_staff)])
def upsert_course(body: CourseIn):
    with connect() as conn:
        conn.execute(
            """INSERT INTO courses (id, code, title, term, created_at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET code = excluded.code, title = excluded.title, term = excluded.term""",
            (body.id, body.code, body.title, body.term, _now()),
        )
    return get_course(body.id)


@router.get("/courses/{course_id}")
def get_course(course_id: str):
    with connect() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if course is None:
            raise HTTPException(404, "Course not found")
        lectures = conn.execute(
            """SELECT l.*, COUNT(s.id) AS slide_count FROM lectures l
               LEFT JOIN slides s ON s.lecture_id = l.id
               WHERE l.course_id = ? GROUP BY l.id ORDER BY l.week, l.held_at, l.title""",
            (course_id,),
        ).fetchall()
    return {
        "id": course["id"],
        "code": course["code"],
        "title": course["title"],
        "term": course["term"],
        "lectures": [
            {"id": l["id"], "week": l["week"], "title": l["title"], "held_at": l["held_at"], "slide_count": l["slide_count"]}
            for l in lectures
        ],
    }


@router.post("/courses/{course_id}/lectures", status_code=201, dependencies=[Depends(require_staff)])
def upsert_lecture(course_id: str, body: LectureIn):
    with connect() as conn:
        if conn.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone() is None:
            raise HTTPException(404, "Course not found")
        existing = conn.execute("SELECT course_id FROM lectures WHERE id = ?", (body.id,)).fetchone()
        if existing is not None and existing["course_id"] != course_id:
            raise HTTPException(409, "Lecture id already used by another course")
        conn.execute(
            """INSERT INTO lectures (id, course_id, week, title, held_at, created_at) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET week = excluded.week, title = excluded.title, held_at = excluded.held_at""",
            (body.id, course_id, body.week, body.title, body.held_at, _now()),
        )
    return get_lecture(body.id)


@router.get("/lectures/{lecture_id}")
def get_lecture(lecture_id: str):
    with connect() as conn:
        lecture = get_lecture_row(conn, lecture_id)
        slides = conn.execute(
            "SELECT * FROM slides WHERE lecture_id = ? ORDER BY slide_number", (lecture_id,)
        ).fetchall()
    return {
        "id": lecture["id"],
        "course_id": lecture["course_id"],
        "week": lecture["week"],
        "title": lecture["title"],
        "held_at": lecture["held_at"],
        "slides": [_slide_dict(s, lecture["week"]) for s in slides],
    }


def write_slides(conn, lecture_id: str, slides: list[SlideIn]) -> None:
    """Replace the lecture's slide text. Images of slides that still exist are kept.

    Used by the REST route and by PDF ingest (ingest.py)."""
    numbers = [s.slide_number for s in slides]
    if len(numbers) != len(set(numbers)):
        raise HTTPException(422, "Duplicate slide_number")
    get_lecture_row(conn, lecture_id)
    if numbers:
        conn.execute(
            f"DELETE FROM slides WHERE lecture_id = ? AND slide_number NOT IN ({','.join('?' * len(numbers))})",
            (lecture_id, *numbers),
        )
    else:
        conn.execute("DELETE FROM slides WHERE lecture_id = ?", (lecture_id,))
    conn.executemany(
        """INSERT INTO slides (lecture_id, slide_number, title, topic, body) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(lecture_id, slide_number) DO UPDATE SET title = excluded.title, topic = excluded.topic, body = excluded.body""",
        [(lecture_id, s.slide_number, s.title, s.topic, s.body) for s in slides],
    )
    search_index.index_lecture(conn, lecture_id)


@router.put("/lectures/{lecture_id}/slides", dependencies=[Depends(require_staff)])
def replace_slides(lecture_id: str, body: SlidesIn):
    """Replace the lecture's slide text. Images of slides that still exist are kept."""
    with connect() as conn:
        write_slides(conn, lecture_id, body.slides)
    return get_lecture(lecture_id)


@router.get("/lectures/{lecture_id}/slides/{slide_number}")
def read_slide(lecture_id: str, slide_number: int):
    with connect() as conn:
        slide = get_slide(conn, lecture_id, slide_number)
    if slide is None:
        raise HTTPException(404, "Slide not found")
    return slide


@router.put("/lectures/{lecture_id}/slides/{slide_number}/image", dependencies=[Depends(require_staff)])
def attach_slide_image(lecture_id: str, slide_number: int, body: ImageIn):
    header, sep, encoded = body.data_url.partition(",")
    mime = header.removeprefix("data:").removesuffix(";base64")
    if not sep or not header.endswith(";base64") or mime not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(422, "Expected a base64 JPEG, PNG or WebP data URL")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Image is not valid base64")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image is larger than 5 MB")
    with connect() as conn:
        cur = conn.execute(
            "UPDATE slides SET image = ?, image_type = ? WHERE lecture_id = ? AND slide_number = ?",
            (data, mime, lecture_id, slide_number),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Slide not found")
        return get_slide(conn, lecture_id, slide_number)


@router.get("/lectures/{lecture_id}/slides/{slide_number}/image")
def read_slide_image(lecture_id: str, slide_number: int):
    with connect() as conn:
        row = conn.execute(
            "SELECT image, image_type FROM slides WHERE lecture_id = ? AND slide_number = ?", (lecture_id, slide_number)
        ).fetchone()
    if row is None or row["image"] is None:
        raise HTTPException(404, "No image for this slide")
    return Response(content=row["image"], media_type=row["image_type"], headers={"Cache-Control": "public, max-age=3600"})


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=500),
    course_id: str | None = None,
    lecture_id: str | None = None,
    limit: int = Query(default=5, ge=1, le=20),
):
    with connect() as conn:
        return search_slides(conn, q, course_id, lecture_id, limit)
