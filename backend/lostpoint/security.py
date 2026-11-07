"""Signed cookies for sessions and OAuth state."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

_session_serializer = URLSafeTimedSerializer(
    settings.session_secret, salt="lostpoint-session"
)
_state_serializer = URLSafeTimedSerializer(
    settings.session_secret, salt="lostpoint-oauth-state"
)

OAUTH_STATE_MAX_AGE = 10 * 60


class InvalidToken(Exception):
    """Raised when a signed cookie cannot be trusted."""


def sign_session_id(session_id: str) -> str:
    return _session_serializer.dumps(session_id)


def unsign_session_id(value: str) -> str:
    try:
        return _session_serializer.loads(value, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired) as exc:
        raise InvalidToken from exc


def sign_oauth_state(nonce: str) -> str:
    return _state_serializer.dumps(nonce)


def unsign_oauth_state(value: str) -> str:
    try:
        return _state_serializer.loads(value, max_age=OAUTH_STATE_MAX_AGE)
    except (BadSignature, SignatureExpired) as exc:
        raise InvalidToken from exc
