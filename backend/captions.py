"""Live captions + translation: WebSocket endpoint and glossary routes.

WebSocket:  /api/ws/captions/{lecture_id}?lang=es&speaker=1&key=...
  * lang     target language for this listener (see translation.LANGUAGES)
  * speaker  1 = this connection is the lecture source (sends interim/final text)
  * key      must match SPEAKER_KEY when that env var is set (use it on the day)

With SPEAKER_KEY unset anyone can become a speaker. That is handy for local
development and a one-laptop demo; set it for anything shared.
"""

from __future__ import annotations

import hmac
import json
import os

import httpx
from fastapi import APIRouter, Header, HTTPException, Path, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from caption_hub import CaptionHub
from config import settings
from translation import LANGUAGES, SOURCE_LANG, GlossaryStore, Translator

glossary = GlossaryStore()
translator = Translator()
hub = CaptionHub(translator, glossary)

SPEAKER_KEY = os.getenv("SPEAKER_KEY", "")
LECTURE_ID = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")

router = APIRouter(prefix="/api")
SCRIBE_TOKEN_URL = "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe"


class GlossaryBody(BaseModel):
    terms: list[str] = Field(max_length=300)


@router.get("/lectures/{lecture_id}/glossary")
def get_glossary(lecture_id: str = LECTURE_ID):
    return {"lecture_id": lecture_id, "terms": glossary.get_terms(lecture_id)}


@router.put("/lectures/{lecture_id}/glossary")
def put_glossary(body: GlossaryBody, lecture_id: str = LECTURE_ID):
    return {"lecture_id": lecture_id, "terms": glossary.set_terms(lecture_id, body.terms)}


@router.get("/captions/status")
def captions_status():
    return {
        "mock": translator.mock,
        "model": translator.model,
        "rooms": {rid: len(room.members) for rid, room in hub.rooms.items()},
    }


@router.post("/captions/scribe-token")
async def scribe_token(speaker_key: str = Header(default="", alias="X-Speaker-Key")):
    """Issue a one-time microphone token without exposing the ElevenLabs API key."""
    if SPEAKER_KEY and not hmac.compare_digest(speaker_key.encode(), SPEAKER_KEY.encode()):
        raise HTTPException(403, "Invalid lecturer key.")
    api_key = settings().elevenlabs_api_key
    if not api_key:
        raise HTTPException(503, "Set ELEVENLABS_API_KEY in backend/.env to use ElevenLabs captions.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(SCRIBE_TOKEN_URL, headers={"xi-api-key": api_key})
            response.raise_for_status()
            payload = response.json()
            token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise ValueError("Missing Scribe token")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        # An upstream error can contain request details; never return it or the key.
        raise HTTPException(502, "Could not start ElevenLabs transcription. Check the API key and try again.") from exc
    return JSONResponse({"token": token}, headers={"Cache-Control": "no-store"})


@router.websocket("/ws/captions/{lecture_id}")
async def captions_ws(
    ws: WebSocket,
    lecture_id: str = LECTURE_ID,
    lang: str = SOURCE_LANG,
    speaker: bool = False,
    key: str = "",
):
    await ws.accept()

    if speaker and SPEAKER_KEY and not hmac.compare_digest(key.encode(), SPEAKER_KEY.encode()):
        await ws.send_json({"type": "error", "code": "bad_key", "message": "Invalid lecturer key."})
        speaker = False
    if lang not in LANGUAGES:
        lang = SOURCE_LANG

    member = await hub.join(lecture_id, ws, lang, speaker)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                await hub.handle(lecture_id, member, msg)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(lecture_id, member)
