"""Configuration loaded from backend/.env and the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    canvas_base_url: str
    canvas_api_token: str
    canvas_client_id: str
    canvas_client_secret: str
    canvas_redirect_uri: str
    frontend_origin: str
    session_secret: str
    database_path: Path
    session_cookie: str
    oauth_state_cookie: str
    session_max_age: int
    cookie_secure: bool
    request_timeout: float
    demo_course_id: int


def load_settings() -> Settings:
    frontend_origin = _get("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")
    redirect_uri = _get("CANVAS_REDIRECT_URI") or f"{frontend_origin}/api/auth/canvas/callback"
    return Settings(
        canvas_base_url=_get("CANVAS_BASE_URL", "http://localhost").rstrip("/"),
        canvas_api_token=_get("CANVAS_API_TOKEN"),
        canvas_client_id=_get("CANVAS_CLIENT_ID"),
        canvas_client_secret=_get("CANVAS_CLIENT_SECRET"),
        canvas_redirect_uri=redirect_uri,
        frontend_origin=frontend_origin,
        session_secret=_get("SESSION_SECRET", "dev-only-change-me"),
        database_path=Path(_get("LOSTPOINT_DB", str(BACKEND_DIR / "lostpoint.db"))),
        session_cookie=_get("SESSION_COOKIE", "lostpoint_session"),
        oauth_state_cookie=_get("OAUTH_STATE_COOKIE", "lostpoint_oauth_state"),
        session_max_age=_get_int("SESSION_MAX_AGE", 7 * 24 * 60 * 60),
        cookie_secure=_get_bool("COOKIE_SECURE", False),
        request_timeout=_get_float("CANVAS_TIMEOUT", 30.0),
        demo_course_id=_get_int("CANVAS_DEMO_COURSE_ID", 1),
    )


settings = load_settings()
