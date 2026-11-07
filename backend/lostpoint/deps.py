"""FastAPI dependencies for the current LostPoint session."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from .config import settings
from .db import Session, get_session as load_session
from .security import InvalidToken, unsign_session_id


def session_from_request(request: Request) -> Session | None:
    raw = request.cookies.get(settings.session_cookie)
    if not raw:
        return None
    try:
        session_id = unsign_session_id(raw)
    except InvalidToken:
        return None
    return load_session(session_id)


def get_session_dep(request: Request) -> Session:
    session = session_from_request(request)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated with Canvas.",
        )
    return session


def get_optional_session(request: Request) -> Session | None:
    return session_from_request(request)
