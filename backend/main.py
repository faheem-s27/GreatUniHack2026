"""FastAPI entry point for the LostPoint backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from coach_store import router as coach_router
from courses import router as courses_router
from coursework import router as coursework_router
from db import init_db
from insights import router as insights_router
from live import router as live_router
from lost_moments import router as lost_moments_router
from memory import router as memory_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LostPoint API", version="0.2.0", lifespan=lifespan)
app.include_router(lost_moments_router)
app.include_router(courses_router)
app.include_router(coursework_router)
app.include_router(memory_router)
app.include_router(coach_router)
app.include_router(insights_router)
app.include_router(live_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
