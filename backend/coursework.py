"""Assessed coursework, so the coach's locked mode is decided in code.

Routes
  GET    /api/courses/{course_id}/coursework           list assessed work
  POST   /api/courses/{course_id}/coursework           create or update one item
  DELETE /api/coursework/{coursework_id}               remove it
  POST   /api/coursework/check                         does this question match assessed work?

check_question() is the function the coach should call (it is also used when a
coach session is created). A question matches an item when it contains any of
the item's keyword phrases as whole words, ignoring case and punctuation.
Keywords should be specific to the assignment, e.g. "x^2 y + sin(xy)" or
"coursework 2 question 3", not general topic words like "derivative",
otherwise every question about the topic gets locked.
"""

import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from accounts import require_staff
from db import connect

router = APIRouter(prefix="/api", tags=["coursework"])


class CourseworkIn(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    due_at: str | None = Field(default=None, max_length=40)


class CheckIn(BaseModel):
    course_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=10_000)


def _normalise(text: str) -> str:
    # Keep maths symbols that matter in questions (^ + - * / = ( )), turn other
    # punctuation into spaces, and drop spaces next to symbols so that
    # "x^2 y + sin(xy)" and "x^2 y+sin( xy )" compare equal.
    text = text.lower()
    text = re.sub(r"[^\w^+\-*/=()]+", " ", text)
    text = re.sub(r"\s*([\^+\-*/=()])\s*", r"\1", text)
    return " ".join(text.split())


def _contains(haystack: str, needle: str) -> bool:
    # Whole-word match: "coursework 1" must not match "coursework 10". Only
    # checked where the keyword starts or ends with a letter or digit, since a
    # keyword ending in ")" may be glued to the next word after normalising.
    before = r"(?<!\w)" if re.match(r"\w", needle) else ""
    after = r"(?!\w)" if re.search(r"\w$", needle) else ""
    return re.search(before + re.escape(needle) + after, haystack) is not None


def _to_dict(row) -> dict:
    return {
        "id": row["id"],
        "course_id": row["course_id"],
        "title": row["title"],
        "description": row["description"],
        "keywords": json.loads(row["keywords"]),
        "due_at": row["due_at"],
    }


def check_question(conn, course_id: str, text: str) -> dict:
    """{"locked": bool, "matches": [{id, title, keyword}]} for a student's question."""
    haystack = _normalise(text)
    matches = []
    for row in conn.execute("SELECT * FROM coursework WHERE course_id = ?", (course_id,)).fetchall():
        for kw in json.loads(row["keywords"]):
            needle = _normalise(kw)
            if needle and _contains(haystack, needle):
                matches.append({"id": row["id"], "title": row["title"], "keyword": kw})
                break
    return {"locked": bool(matches), "matches": matches}


@router.get("/courses/{course_id}/coursework", dependencies=[Depends(require_staff)])
def list_coursework(course_id: str):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM coursework WHERE course_id = ? ORDER BY due_at, title", (course_id,)).fetchall()
    return [_to_dict(r) for r in rows]


@router.post("/courses/{course_id}/coursework", status_code=201, dependencies=[Depends(require_staff)])
def upsert_coursework(course_id: str, body: CourseworkIn):
    keywords = [k.strip() for k in body.keywords if k.strip()]
    with connect() as conn:
        if conn.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone() is None:
            raise HTTPException(404, "Course not found")
        existing = conn.execute("SELECT course_id FROM coursework WHERE id = ?", (body.id,)).fetchone()
        if existing is not None and existing["course_id"] != course_id:
            raise HTTPException(409, "Coursework id already used by another course")
        conn.execute(
            """INSERT INTO coursework (id, course_id, title, description, keywords, due_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET title = excluded.title, description = excluded.description,
                   keywords = excluded.keywords, due_at = excluded.due_at""",
            (body.id, course_id, body.title, body.description, json.dumps(keywords), body.due_at, datetime.now(timezone.utc).isoformat()),
        )
        return _to_dict(conn.execute("SELECT * FROM coursework WHERE id = ?", (body.id,)).fetchone())


@router.delete("/coursework/{coursework_id}", status_code=204, dependencies=[Depends(require_staff)])
def delete_coursework(coursework_id: str):
    with connect() as conn:
        if conn.execute("DELETE FROM coursework WHERE id = ?", (coursework_id,)).rowcount == 0:
            raise HTTPException(404, "Coursework not found")


@router.post("/coursework/check")
def check(body: CheckIn):
    with connect() as conn:
        return check_question(conn, body.course_id, body.text)
