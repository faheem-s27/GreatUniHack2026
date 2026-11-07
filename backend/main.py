"""FastAPI entry point for the LostPoint backend.

Run locally:      uvicorn main:app --reload --reload-exclude .venv
Run in Docker:    see Dockerfile at the repository root (serves the built frontend too)
Settings:         config.py, from environment variables
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from accounts import router as accounts_router
from captions import router as captions_router
from coach_store import router as coach_router
from config import settings
from courses import router as courses_router
from coursework import router as coursework_router
from db import connect, init_db
from events import router as events_router
from handoffs import router as handoffs_router
from ingest import router as ingest_router
from insights import router as insights_router
from live import router as live_router
from lost_moments import router as lost_moments_router
from memory import router as memory_router

VERSION = "0.3.0"

logging.basicConfig(level=settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lostpoint")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    log.info("LostPoint %s started, database %s, search %s", VERSION, settings().db_path, settings().search)
    yield


app = FastAPI(title="LostPoint API", version=VERSION, lifespan=lifespan)

if settings().cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Something went wrong on our side. Please try again.", "status": 500}, status_code=500)
    if request.url.path.startswith("/api"):
        log.info("%s %s %d %.0fms", request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000)
    return response


# Every error has the same shape, {"detail": ..., "status": ...}, so the frontend
# can show error.detail whatever went wrong.
@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail, "status": exc.status_code}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    first = errors[0] if errors else {"field": "", "message": "Invalid request"}
    detail = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
    return JSONResponse({"detail": detail, "status": 422, "errors": errors}, status_code=422)


for router in (accounts_router, lost_moments_router, courses_router, ingest_router, coursework_router, memory_router,
               coach_router, insights_router, handoffs_router, events_router, live_router, captions_router):
    app.include_router(router)


@app.get("/api/health")
def health():
    """For load balancers and the Docker HEALTHCHECK: checks the database too."""
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    body = {"status": "ok" if db_ok else "degraded", "version": VERSION, "database": db_ok, "search": settings().search}
    return JSONResponse(body, status_code=200 if db_ok else 503)


# In production the built frontend is served from the same origin, so /api and
# /ws need no CORS and no proxy. Unknown paths fall back to index.html.
static_dir = settings().static_dir
if static_dir and os.path.isdir(static_dir):
    root = os.path.realpath(static_dir)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith(("api/", "ws/")):
            raise HTTPException(404, "Not found")
        target = os.path.realpath(os.path.join(root, path))
        if path and target.startswith(root + os.sep) and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(root, "index.html"))
