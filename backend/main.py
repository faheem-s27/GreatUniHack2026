"""FastAPI entry point for the LostPoint backend."""

from fastapi import FastAPI

app = FastAPI(title="LostPoint API", version="0.1.0")


@app.get("/api/health")
def health():
    return {"status": "ok"}
