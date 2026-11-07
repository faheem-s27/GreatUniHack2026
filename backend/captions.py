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

from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from caption_hub import CaptionHub
from translation import LANGUAGES, SOURCE_LANG, GlossaryStore, Translator

glossary = GlossaryStore()
translator = Translator()
hub = CaptionHub(translator, glossary)

SPEAKER_KEY = os.getenv("SPEAKER_KEY", "")
LECTURE_ID = Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")

router = APIRouter(prefix="/api")


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
