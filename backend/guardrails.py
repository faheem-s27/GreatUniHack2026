"""Deterministic policy and response validation for the coach."""

from dataclasses import dataclass, field
from enum import Enum
import re


class Mode(str, Enum):
    GUIDE = "GUIDE"
    EXPLAIN = "EXPLAIN"
    LOCKED = "LOCKED"


@dataclass(frozen=True)
class Slide:
    number: int
    text: str
    assessed: bool = False


@dataclass
class Session:
    concept: str
    failed_attempts: int = 0
    assessed: bool = False
    gap_closed: bool = False
    last_question: str = ""
    attempts: set[str] = field(default_factory=set)
    history: list[tuple[str, str]] = field(default_factory=list)


def pick_mode(session: Session, slides: list[Slide]) -> Mode:
    # Once assessed, this session stays locked even if retrieval changes.
    if session.assessed or any(slide.assessed for slide in slides):
        return Mode.LOCKED
    if session.failed_attempts >= 3:
        return Mode.EXPLAIN
    return Mode.GUIDE


def valid_citations(reply: str, slides: list[Slide]) -> bool:
    citations = re.findall(r"\bslide\s+(\d+)\b", reply, flags=re.IGNORECASE)
    available = {str(slide.number) for slide in slides}
    return bool(citations) and all(number in available for number in citations)


def normalized_attempt(message: str) -> str:
    return " ".join(message.casefold().split())


def safe_fallback(slides: list[Slide]) -> str:
    if not slides:
        return "I couldn't find a relevant slide. Please try again when the lecture slides are available."
    return (f"Let's take this one step at a time. Look at slide {slides[0].number}: "
            "what is one part of the idea that you can describe in your own words?")
