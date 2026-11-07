"""FastAPI entry point for the LostPoint backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import init_db
from lost_moments import router as lost_moments_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="LostPoint API", version="0.1.0", lifespan=lifespan)
app.include_router(lost_moments_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
