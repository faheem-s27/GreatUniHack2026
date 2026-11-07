"""The AI coach over HTTP, grounded in a lecture's real slides.

  POST /api/coach
    {student_id | session_id, lecture_id?, slide_number, message, concept?}
    -> {mode, response, wrong_attempts, gap_closed, citations, source, provider, lecture_id, concept}

How a reply is built (Stephanie's Coach does the tutoring; this module feeds it):
  1. Slides: with a lecture_id, the student's current slide plus the best
     matches for their question, searched only inside that lecture
     (courses.search_slides with lecture_id), so two lectures never see each
     other's slides. Without a lecture_id the server-owned demo slides are used
     and the response says source="demo".
  2. Assessed status, decided here and never by the browser: the lecture was
     uploaded as coursework (library.py), or the question matches the course's
     assessed coursework (coursework.check_question). Assessed slides put the
     session in LOCKED mode, and it stays locked.
  3. Citations: the Coach only accepts "slide N" for slides it was given, so it
     cannot cite a slide from another lecture or one that does not exist.
  4. Memory: the Coach's session (attempts, mode inputs, history) is stored per
     student, lecture and concept in SQLite (coach_memory). Failed attempts and
     closed gaps also update the student memory (memory.py), which drives the
     tutor handoff and the metrics.

A lecture with no readable slides gets a clear answer (source="none") instead
of a made-up one, and no AI call is made.

Provider: Anthropic when ANTHROPIC_API_KEY is set (backend/.env). Set
LOSTPOINT_COACH_PROVIDER=fake for the scripted offline demo provider. Without
either, the coach answers 503 with a setup hint; the key never reaches the browser.
"""

import json
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from coach import AnthropicProvider, Coach, FakeProvider
from courses import get_slide, search_slides
from coursework import check_question
from db import connect
from demo_lecture import DEMO_LECTURE_ID, DEMO_SLIDES, slides_for
from guardrails import Mode, Session, Slide
from library import is_assessed_lecture
from memory import add_attempt, concept_key, record_gap, set_gap_status

router = APIRouter(prefix="/api", tags=["coach"])

RETRIEVE = 4  # slides found by the question, besides the current slide
DEMO_CONCEPT = "partial derivatives"


class CoachRequest(BaseModel):
    # Unknown fields are rejected, so the browser cannot send "assessed": false.
    model_config = ConfigDict(extra="forbid")

    student_id: str | None = Field(default=None, min_length=1, max_length=64)
    session_id: UUID | None = None  # older demo clients send a per-page-load id instead
    lecture_id: str | None = Field(default=None, max_length=64)
    slide_number: int = Field(ge=1, le=10_000)
    message: str = Field(min_length=1, max_length=2000)
    concept: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _who(self):
        if not self.student_id and not self.session_id:
            raise ValueError("student_id is required")
        return self


class CoachResponse(BaseModel):
    mode: Mode
    response: str
    wrong_attempts: int
    gap_closed: bool
    citations: list[dict]
    source: str           # "lecture" (uploaded slides), "demo" (built-in demo slides) or "none"
    provider: str         # "anthropic" or "fake"
    lecture_id: str
    concept: str


@lru_cache(maxsize=1)
def get_provider():
    # Lazy, so the API starts without a key; created once and reused.
    if os.environ.get("LOSTPOINT_COACH_PROVIDER", "").lower() == "fake":
        return FakeProvider()
    return AnthropicProvider()


# ---- memory: Stephanie's Session, stored in SQLite ------------------------------

def _key(concept: str) -> str:
    return " ".join(concept.lower().split())


class SqliteCoachStore:
    """Same interface as coach.MemoryStore, but survives restarts."""

    def __init__(self, conn):
        self.conn = conn

    def get(self, student_id: str, lecture_id: str, concept: str) -> Session:
        row = self.conn.execute(
            "SELECT state FROM coach_memory WHERE student_id = ? AND lecture_id = ? AND concept_key = ?",
            (student_id, lecture_id, _key(concept)),
        ).fetchone()
        if row is None:
            return Session(concept=concept)
        data = json.loads(row["state"])
        data["attempts"] = set(data.get("attempts", []))
        data["history"] = [tuple(pair) for pair in data.get("history", [])]
        return Session(**data)

    def save(self, student_id: str, lecture_id: str, session: Session) -> None:
        state = asdict(session)
        state["attempts"] = sorted(session.attempts)
        state["history"] = [list(pair) for pair in session.history[-20:]]
        self.conn.execute(
            """INSERT INTO coach_memory (student_id, lecture_id, concept_key, state, updated_at) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(student_id, lecture_id, concept_key) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at""",
            (student_id, lecture_id, _key(session.concept), json.dumps(state), datetime.now(timezone.utc).isoformat()),
        )


# ---- slides --------------------------------------------------------------------

def _slide_text(hit: dict) -> str:
    return "\n".join(filter(None, [hit.get("title"), hit.get("topic"), hit.get("body")]))


def lecture_slides(conn, lecture_id: str, slide_number: int, question: str) -> tuple[list[Slide], dict, str]:
    """(slides for the Coach, slide titles by number, course_id). Only this lecture's slides."""
    lecture = conn.execute("SELECT course_id FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
    if lecture is None:
        raise HTTPException(404, "Lecture not found. Upload its slides first.")
    course_id = lecture["course_id"]
    hits = []
    current = get_slide(conn, lecture_id, slide_number)
    if current and _slide_text(current).strip():
        hits.append(current)
    for hit in search_slides(conn, question, lecture_id=lecture_id, limit=RETRIEVE):
        if hit["slide_number"] not in {h["slide_number"] for h in hits}:
            full = get_slide(conn, lecture_id, hit["slide_number"])
            if full and _slide_text(full).strip():
                hits.append(full)
    # Assessed status comes from the server only: an uploaded coursework PDF,
    # or a question that matches the course's assessed coursework.
    assessed = is_assessed_lecture(conn, lecture_id) or check_question(conn, course_id, question)["locked"]
    slides = [Slide(h["slide_number"], _slide_text(h)[:3000], assessed) for h in hits]
    titles = {h["slide_number"]: h.get("title") for h in hits}
    return slides, titles, course_id


def _concept(conn, lecture_id: str, slide_number: int, given: str | None) -> str:
    if given and given.strip():
        return given.strip()
    slide = get_slide(conn, lecture_id, slide_number)
    if slide and (slide.get("topic") or slide.get("title")):
        return slide.get("topic") or slide.get("title")
    title = conn.execute("SELECT title FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
    return f"{title['title'] if title else lecture_id}, slide {slide_number}"


def _citations(response: str, titles: dict) -> list[dict]:
    seen = []
    for n in re.findall(r"\bslide\s+(\d+)\b", response, flags=re.IGNORECASE):
        n = int(n)
        if n in titles and n not in [c["slide_number"] for c in seen]:
            seen.append({"slide_number": n, "title": titles[n]})
    return seen


@router.post("/coach", response_model=CoachResponse)
def coach_reply(request: CoachRequest):
    student_id = request.student_id or str(request.session_id)
    message = request.message.strip()
    if not message:
        raise HTTPException(422, "Please enter a message.")

    with connect() as conn:
        if request.lecture_id:
            lecture_id = request.lecture_id
            slides, titles, course_id = lecture_slides(conn, lecture_id, request.slide_number, message)
            concept = _concept(conn, lecture_id, request.slide_number, request.concept)
            source = "lecture" if slides else "none"
        else:
            if request.slide_number not in DEMO_SLIDES:
                raise HTTPException(422, "Choose a slide from the demo lecture.")
            lecture_id, course_id, concept, source = DEMO_LECTURE_ID, None, request.concept or DEMO_CONCEPT, "demo"
            slides = slides_for(request.slide_number)
            titles = {s.number: None for s in slides}

        store = SqliteCoachStore(conn)
        if source == "none":
            # Nothing to ground an answer in: say so instead of guessing.
            return CoachResponse(
                mode=Mode.GUIDE, response="I can't read any text on this lecture's slides yet, so I can't guide you "
                "from them. If the PDF is scanned or image-only, try a version with selectable text.",
                wrong_attempts=0, gap_closed=False, citations=[], source="none", provider="none",
                lecture_id=lecture_id, concept=concept,
            )

        before = store.get(student_id, lecture_id, concept)
        try:
            provider = get_provider()
            mode, response = Coach(provider, search=lambda _lecture, _q: slides, store=store).reply(
                student_id, lecture_id, concept, message)
        except (ImportError, ValueError) as exc:
            raise HTTPException(503, "The coach isn't set up on the server yet. Add ANTHROPIC_API_KEY to "
                                     "backend/.env, or set LOSTPOINT_COACH_PROVIDER=fake for the offline demo.") from exc
        except Exception as exc:  # upstream API errors: never echo request bodies or keys
            raise HTTPException(503, "The coach is unavailable right now. Please try again in a moment.") from exc

        after = store.get(student_id, lecture_id, concept)
        if course_id:  # feed the student memory, tutor handoff and metrics
            # Look the gap up first: record_gap would reopen a gap the student already closed.
            row = conn.execute(
                "SELECT id FROM gaps WHERE student_id = ? AND course_id = ? AND concept_key = ?",
                (student_id, course_id, concept_key(concept)),
            ).fetchone()
            gap_id = row["id"] if row else record_gap(conn, student_id, course_id, concept, lecture_id, request.slide_number)["id"]
            for _ in range(after.failed_attempts - before.failed_attempts):
                add_attempt(conn, gap_id)
            if after.gap_closed and not before.gap_closed:
                set_gap_status(conn, gap_id, "closed")

        return CoachResponse(
            mode=mode, response=response, wrong_attempts=after.failed_attempts, gap_closed=after.gap_closed,
            citations=_citations(response, titles) if source == "lecture" else [], source=source,
            provider="fake" if isinstance(provider, FakeProvider) else "anthropic",
            lecture_id=lecture_id, concept=concept,
        )
