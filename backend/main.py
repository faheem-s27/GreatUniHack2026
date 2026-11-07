"""FastAPI entry point for the LostPoint backend."""

from fastapi import FastAPI

from captions import router as captions_router

app = FastAPI(title="LostPoint API", version="0.1.0")
app.include_router(captions_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
