"""FastAPI application for the LostPoint backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .canvas import CanvasError
from .config import settings
from .db import delete_session, init_db, purge_expired
from .routes_auth import router as auth_router
from .routes_canvas import router as canvas_router
from .security import InvalidToken, unsign_session_id


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    purge_expired()
    yield


app = FastAPI(title="LostPoint API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(canvas_router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "canvas": {
            "base_url": settings.canvas_base_url,
            "oauth_configured": bool(
                settings.canvas_client_id and settings.canvas_client_secret
            ),
        },
    }


@app.exception_handler(CanvasError)
async def canvas_error_handler(
    request: Request, exc: CanvasError
) -> JSONResponse:
    status_code = exc.status_code if exc.status_code in {401, 403, 404} else 502
    response = JSONResponse(
        status_code=status_code, content={"detail": exc.message}
    )
    if exc.status_code == 401:
        raw = request.cookies.get(settings.session_cookie)
        if raw:
            try:
                delete_session(unsign_session_id(raw))
            except InvalidToken:
                pass
        response.delete_cookie(settings.session_cookie, path="/")
    return response
