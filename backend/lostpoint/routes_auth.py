"""Canvas OAuth2 login, logout, and current-user endpoints."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .canvas import CanvasError
from .config import settings
from .db import Session, create_session, delete_session
from .deps import get_optional_session
from .security import (
    InvalidToken,
    sign_oauth_state,
    sign_session_id,
    unsign_oauth_state,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _frontend_redirect(status: str, message: str = "") -> RedirectResponse:
    params = {"canvas_auth": status}
    if message:
        params["message"] = message
    response = RedirectResponse(
        f"{settings.frontend_origin}/?{urlencode(params)}", status_code=302
    )
    response.delete_cookie(settings.oauth_state_cookie, path="/")
    return response


@router.get("/canvas/login")
def canvas_login() -> RedirectResponse:
    """Send the browser to Canvas so the student can sign in and approve access."""
    if not settings.canvas_client_id or not settings.canvas_client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Canvas OAuth is not configured. Run "
                "backend/scripts/setup_canvas_oauth.py first."
            ),
        )

    state = sign_oauth_state(secrets.token_urlsafe(24))
    params = {
        "client_id": settings.canvas_client_id,
        "response_type": "code",
        "redirect_uri": settings.canvas_redirect_uri,
        "state": state,
        "purpose": "LostPoint slide access",
    }
    location = f"{settings.canvas_base_url}/login/oauth2/auth?{urlencode(params)}"
    response = RedirectResponse(location, status_code=302)
    response.set_cookie(
        settings.oauth_state_cookie,
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return response


@router.get("/canvas/callback")
def canvas_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Exchange Canvas's authorization code for an access token."""
    if error:
        return _frontend_redirect("error", error_description or error)

    state_cookie = request.cookies.get(settings.oauth_state_cookie)
    if (
        not code
        or not state
        or not state_cookie
        or not secrets.compare_digest(state, state_cookie)
    ):
        return _frontend_redirect(
            "error", "The Canvas login response was invalid or expired."
        )

    try:
        unsign_oauth_state(state)
    except InvalidToken:
        return _frontend_redirect(
            "error", "The Canvas login response expired. Please try again."
        )

    try:
        token = _exchange_code(code)
    except CanvasError as exc:
        return _frontend_redirect("error", exc.message)

    access_token = token.get("access_token")
    user = token.get("user") or {}
    if not access_token:
        return _frontend_redirect("error", "Canvas did not return an access token.")

    session_id = create_session(
        canvas_user_id=user.get("id"),
        canvas_user_name=user.get("name"),
        canvas_user_email=user.get("email") or user.get("login_id"),
        access_token=access_token,
        refresh_token=token.get("refresh_token"),
    )

    response = RedirectResponse(
        f"{settings.frontend_origin}/?canvas_auth=success", status_code=302
    )
    response.delete_cookie(settings.oauth_state_cookie, path="/")
    response.set_cookie(
        settings.session_cookie,
        sign_session_id(session_id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return response


def _exchange_code(code: str) -> dict:
    try:
        with httpx.Client(timeout=settings.request_timeout) as client:
            response = client.post(
                f"{settings.canvas_base_url}/login/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.canvas_client_id,
                    "client_secret": settings.canvas_client_secret,
                    "redirect_uri": settings.canvas_redirect_uri,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise CanvasError(
            502, f"Could not reach Canvas to exchange the login code: {exc}"
        ) from exc

    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = (
            payload.get("error_description")
            or payload.get("error")
            or response.text[:300]
        )
        raise CanvasError(502, f"Canvas rejected the login code: {message}")

    try:
        return response.json()
    except ValueError as exc:
        raise CanvasError(502, "Canvas returned an invalid token response.") from exc


@router.get("/me")
def me(session: Session | None = Depends(get_optional_session)) -> dict:
    if session is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": {
            "id": session.canvas_user_id,
            "name": session.canvas_user_name,
            "email": session.canvas_user_email,
        },
        "canvas": {"base_url": settings.canvas_base_url},
    }


@router.post("/logout")
def logout(session: Session | None = Depends(get_optional_session)) -> JSONResponse:
    if session is not None:
        # Best-effort revoke of the Canvas OAuth token. Local session cleanup is
        # what matters if Canvas is unavailable.
        try:
            with httpx.Client(timeout=5) as client:
                client.delete(
                    f"{settings.canvas_base_url}/login/oauth2/token",
                    headers={"Authorization": f"Bearer {session.access_token}"},
                )
        except httpx.HTTPError:
            pass
        delete_session(session.id)

    response = JSONResponse({"ok": True})
    response.delete_cookie(settings.session_cookie, path="/")
    return response
