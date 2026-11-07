"""FastAPI entry point for the LostPoint backend."""

from functools import lru_cache
from uuid import UUID

from anthropic import APIError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from coach import AnthropicProvider, Coach, DEMO_CONCEPT, MemoryStore
from demo_lecture import DEMO_LECTURE_ID, DEMO_SLIDES, slides_for
from guardrails import Mode

app = FastAPI(title="LostPoint API", version="0.1.0")
store = MemoryStore()


class CoachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    slide_number: int
    message: str = Field(min_length=1, max_length=2000)


class CoachResponse(BaseModel):
    mode: Mode
    response: str
    wrong_attempts: int
    gap_closed: bool


@lru_cache(maxsize=1)
def get_provider() -> AnthropicProvider:
    # Lazy initialization keeps /api/health available when no API key is set.
    return AnthropicProvider()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/coach", response_model=CoachResponse)
def coach_reply(request: CoachRequest):
    if request.slide_number not in DEMO_SLIDES:
        raise HTTPException(status_code=422, detail="Choose a slide from the demo lecture.")
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Please enter a message.")

    try:
        provider = get_provider()
        coach = Coach(provider, search=lambda lecture_id, question: slides_for(request.slide_number), store=store)
        student_id = str(request.session_id)
        mode, response = coach.reply(student_id, DEMO_LECTURE_ID, DEMO_CONCEPT, request.message)
    except (APIError, ImportError, ValueError) as exc:
        # Never return upstream request bodies or credentials to the browser.
        raise HTTPException(status_code=503, detail="Coach is unavailable. Check the backend API configuration.") from exc

    session = store.get(student_id, DEMO_LECTURE_ID, DEMO_CONCEPT)
    return CoachResponse(mode=mode, response=response, wrong_attempts=session.failed_attempts,
                         gap_closed=session.gap_closed)
