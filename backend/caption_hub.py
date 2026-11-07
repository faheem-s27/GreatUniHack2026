"""Caption rooms: fan lecture text out to listeners, translating once per language.

Protocol (JSON over WebSocket, see captions.py for the endpoint):

  server -> client
    hello        {lecture_id, lang, source_lang, speaker, slide, mock, languages}
    presence     {listeners, speaker_active}
    slide        {slide}
    interim      {text}                      live, still-changing line (original only)
    caption      {id, original, slide}       finished line, sent immediately
    translation  {id, lang, text, failed}    arrives after `caption`, per language
    error        {code, message}

  client -> server
    set_language {lang}                      any client
    interim      {text}                      speakers only
    final        {text, slide?}              speakers only
    slide        {slide}                     speakers only

Design notes:
  * The original line is shown instantly; translations follow (keyed by id), so
    captions never wait on the LLM.
  * A line is translated once per language in the room, not once per student.
  * Audio never reaches the server. Only text is relayed, and only a few recent
    lines are kept in memory (no database, nothing written to disk).
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from translation import LANGUAGES, SOURCE_LANG, GlossaryStore, Translator, language_list

logger = logging.getLogger("lostpoint.captions")

MAX_TEXT = 600  # characters per caption line
RECENT_LINES = 5  # replayed to late joiners / language switchers
CONTEXT_LINES = 4  # earlier lines handed to the translator for coherence
MAX_SLIDE = 999


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...


@dataclass(eq=False)
class Member:
    ws: Socket
    lang: str = SOURCE_LANG
    speaker: bool = False


class Room:
    def __init__(self, lecture_id: str) -> None:
        self.id = lecture_id
        self.members: set[Member] = set()
        self.slide: int | None = None
        self.seq = 0
        self.history: deque[str] = deque(maxlen=CONTEXT_LINES)
        self.recent: deque[dict] = deque(maxlen=RECENT_LINES)
        self.tasks: set[asyncio.Task] = set()


def _clean(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())[:MAX_TEXT]


def _valid_slide(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= MAX_SLIDE else None


class CaptionHub:
    def __init__(self, translator: Translator, glossary: GlossaryStore) -> None:
        self.translator = translator
        self.glossary = glossary
        self.rooms: dict[str, Room] = {}

    # ---- membership -------------------------------------------------------

    async def join(self, lecture_id: str, ws: Socket, lang: str, speaker: bool) -> Member:
        room = self.rooms.setdefault(lecture_id, Room(lecture_id))
        member = Member(ws=ws, lang=lang if lang in LANGUAGES else SOURCE_LANG, speaker=speaker)
        room.members.add(member)
        await self._send(
            member,
            {
                "type": "hello",
                "lecture_id": lecture_id,
                "lang": member.lang,
                "source_lang": SOURCE_LANG,
                "speaker": member.speaker,
                "slide": room.slide,
                "mock": self.translator.mock,
                "languages": language_list(),
            },
        )
        await self._send_recent(room, member)
        await self._broadcast_presence(room)
        return member

    async def leave(self, lecture_id: str, member: Member) -> None:
        room = self.rooms.get(lecture_id)
        if room is None:
            return
        room.members.discard(member)
        if not room.members:
            for task in list(room.tasks):
                task.cancel()
            self.rooms.pop(lecture_id, None)  # nothing is kept once the room is empty
            return
        await self._broadcast_presence(room)

    # ---- incoming messages ------------------------------------------------

    async def handle(self, lecture_id: str, member: Member, msg: dict) -> None:
        room = self.rooms.get(lecture_id)
        if room is None or member not in room.members:
            return
        kind = msg.get("type")

        if kind == "set_language":
            lang = msg.get("lang")
            if lang in LANGUAGES and lang != member.lang:
                member.lang = lang
                await self._send_recent(room, member)
            return

        if kind in ("interim", "final", "slide"):
            if not member.speaker:
                await self._send(member, {"type": "error", "code": "not_speaker", "message": "This connection is not the lecture source."})
                return
            if kind == "interim":
                text = _clean(msg.get("text"))
                await self._broadcast(room, {"type": "interim", "text": text})
            elif kind == "slide":
                slide = _valid_slide(msg.get("slide"))
                if slide is not None and slide != room.slide:
                    room.slide = slide
                    await self._broadcast(room, {"type": "slide", "slide": slide})
            else:
                await self._publish_final(room, _clean(msg.get("text")), _valid_slide(msg.get("slide")))

    # ---- publishing -------------------------------------------------------

    async def _publish_final(self, room: Room, text: str, slide: int | None) -> None:
        if not text:
            return
        if slide is not None:
            room.slide = slide
        room.seq += 1
        caption = {"id": room.seq, "original": text, "slide": room.slide}
        context = list(room.history)
        room.history.append(text)
        room.recent.append(caption)

        await self._broadcast(room, {"type": "interim", "text": ""})
        await self._broadcast(room, {"type": "caption", **caption})

        for lang in {m.lang for m in room.members if m.lang != SOURCE_LANG}:
            self._spawn(room, self._translate_to_room(room, caption["id"], text, lang, context))

    async def _translate_to_room(self, room: Room, cid: int, text: str, lang: str, context: list[str]) -> None:
        out = await self.translator.translate(text, lang, self.glossary.get_terms(room.id), context)
        await self._broadcast(
            room,
            {"type": "translation", "id": cid, "lang": lang, "text": out, "failed": out is None},
            only_lang=lang,
        )

    async def _translate_to_member(self, room: Room, member: Member, caption: dict, lang: str) -> None:
        out = await self.translator.translate(caption["original"], lang, self.glossary.get_terms(room.id))
        if member.lang == lang:
            await self._send(
                member,
                {"type": "translation", "id": caption["id"], "lang": lang, "text": out, "failed": out is None},
            )

    async def _send_recent(self, room: Room, member: Member) -> None:
        """Catch a late joiner (or a language switcher) up on the last few lines."""
        recent = list(room.recent)
        for caption in recent:
            await self._send(member, {"type": "caption", **caption})
        if member.lang != SOURCE_LANG:
            for caption in recent:
                self._spawn(room, self._translate_to_member(room, member, caption, member.lang))

    async def _broadcast_presence(self, room: Room) -> None:
        await self._broadcast(
            room,
            {
                "type": "presence",
                "listeners": len(room.members),
                "speaker_active": any(m.speaker for m in room.members),
            },
        )

    # ---- plumbing ---------------------------------------------------------

    def _spawn(self, room: Room, coro) -> None:
        task = asyncio.create_task(coro)
        room.tasks.add(task)
        task.add_done_callback(room.tasks.discard)

    async def _send(self, member: Member, data: dict) -> None:
        try:
            await member.ws.send_json(data)
        except Exception:  # a dead socket is cleaned up by its own receive loop
            logger.debug("send failed", exc_info=True)

    async def _broadcast(self, room: Room, data: dict, only_lang: str | None = None) -> None:
        targets = [m for m in list(room.members) if only_lang is None or m.lang == only_lang]
        if targets:
            await asyncio.gather(*(self._send(m, data) for m in targets))
