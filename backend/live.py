"""Live lecture connection: one WebSocket room per lecture.

  WS  /ws/lectures/{lecture_id}?role=lecturer&token=...   (a lecturer or tutor login token)
  WS  /ws/lectures/{lecture_id}?role=student&student_id=...
  GET /api/lectures/{lecture_id}/live          room state over REST (for polling or a quick check)

Every message is JSON with a "type".

Lecturer sends
  {"type": "start"}                             starts the lecture clock (lost taps get lecture_time_s)
  {"type": "slide", "slide_number": 14}          moves everyone to a slide
  {"type": "caption", "text": "...", "final": true, "lang": "en"}
                                                 a caption line; relayed to everyone, never stored
  {"type": "end"}                                ends the live lecture
Student sends
  {"type": "lost", "topic": "...", "id": "client-id"}
                                                 one tap, saved exactly like POST /api/lost-moments
                                                 on the room's current slide
Everyone sends
  {"type": "ping"}                               answered with {"type": "pong"}

Server sends
  {"type": "state", "slide_number", "started", "attendance", "online"}   on join and on changes
  {"type": "slide", "slide_number"}                                      to everyone
  {"type": "caption", "text", "final", "lang", "slide_number"}           to everyone
  {"type": "lost_saved", "moment", "created"}                            to the student who tapped
  {"type": "lost_count", "slide_number", "students", "hidden"}           to lecturers only; distinct
                                                                         students lost on that slide, hidden
                                                                         under HEATMAP_MIN_STUDENTS
  {"type": "error", "detail"}                                            bad message; the socket stays open
  {"type": "ended"}                                                      the lecturer ended the lecture

Rooms live in memory, so they reset when the server restarts. Attendance (who
joined) is stored so the heatmap can show what share of the room got lost.
Captions are relayed only: audio is never received and caption text is never
written anywhere, as the brief's consent rule requires.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from accounts import STAFF, user_for_token
from db import connect
from lost_moments import HEATMAP_MIN_STUDENTS, LostMomentIn, save_moment

log = logging.getLogger("lostpoint.live")
router = APIRouter(tags=["live lecture"])

MAX_MESSAGE_CHARS = 4000


@dataclass
class Room:
    lecture_id: str
    slide_number: int = 1
    started_at: float | None = None  # monotonic clock, for lecture_time_s
    lecturers: set = field(default_factory=set)
    students: dict = field(default_factory=dict)  # websocket -> student_id

    def online(self) -> int:
        return len(set(self.students.values()))


rooms: dict[str, Room] = {}


def _room(lecture_id: str) -> Room:
    if lecture_id not in rooms:
        rooms[lecture_id] = Room(lecture_id)
    return rooms[lecture_id]


async def _send(ws: WebSocket, message: dict) -> None:
    try:
        await ws.send_json(message)
    except Exception:  # a socket that just closed; its own handler cleans up
        pass


async def _broadcast(room: Room, message: dict, lecturers_only: bool = False) -> None:
    targets = list(room.lecturers) + ([] if lecturers_only else list(room.students))
    await asyncio.gather(*(_send(ws, message) for ws in targets))


def _attendance(lecture_id: str) -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM lecture_attendance WHERE lecture_id = ?", (lecture_id,)).fetchone()[0]


def _record_attendance(lecture_id: str, student_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO lecture_attendance (lecture_id, student_id, first_joined_at) VALUES (?, ?, ?)",
            (lecture_id, student_id, datetime.now(timezone.utc).isoformat()),
        )


def _lost_count(lecture_id: str, slide_number: int) -> int:
    with connect() as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT student_id) FROM lost_moments WHERE lecture_id = ? AND slide_number = ?",
            (lecture_id, slide_number),
        ).fetchone()[0]


def _save_tap(body: LostMomentIn) -> tuple[dict, bool]:
    with connect() as conn:
        return save_moment(conn, body)


async def _state(room: Room) -> dict:
    return {
        "type": "state",
        "lecture_id": room.lecture_id,
        "slide_number": room.slide_number,
        "started": room.started_at is not None,
        "attendance": await run_in_threadpool(_attendance, room.lecture_id),
        "online": room.online(),
    }


@router.get("/api/lectures/{lecture_id}/live")
async def live_state(lecture_id: str):
    room = rooms.get(lecture_id) or Room(lecture_id)
    return await _state(room)


async def _handle_lecturer(room: Room, ws: WebSocket, msg: dict) -> None:
    kind = msg.get("type")
    if kind == "start":
        room.started_at = time.monotonic()
        await _broadcast(room, await _state(room))
    elif kind == "slide":
        n = msg.get("slide_number")
        if not isinstance(n, int) or not 1 <= n <= 10_000:
            return await _send(ws, {"type": "error", "detail": "slide_number must be an integer from 1"})
        room.slide_number = n
        await _broadcast(room, {"type": "slide", "slide_number": n})
    elif kind == "caption":
        text = msg.get("text")
        if not isinstance(text, str) or not text.strip():
            return await _send(ws, {"type": "error", "detail": "caption needs text"})
        await _broadcast(room, {
            "type": "caption",
            "text": text[:MAX_MESSAGE_CHARS],
            "final": bool(msg.get("final", True)),
            "lang": str(msg.get("lang") or "en")[:16],
            "slide_number": room.slide_number,
        })
    elif kind == "end":
        await _broadcast(room, {"type": "ended"})
        room.started_at = None
    else:
        await _send(ws, {"type": "error", "detail": f"Unknown message type for a lecturer: {kind}"})


async def _handle_student(room: Room, ws: WebSocket, student_id: str, msg: dict) -> None:
    if msg.get("type") != "lost":
        return await _send(ws, {"type": "error", "detail": f"Unknown message type for a student: {msg.get('type')}"})
    elapsed = int(time.monotonic() - room.started_at) if room.started_at is not None else None
    try:
        body = LostMomentIn(
            student_id=student_id,
            lecture_id=room.lecture_id,
            slide_number=room.slide_number,
            topic=msg.get("topic"),
            lecture_time_s=elapsed,
            id=msg.get("id"),
        )
        moment, created = await run_in_threadpool(_save_tap, body)
    except ValidationError as e:
        return await _send(ws, {"type": "error", "detail": e.errors()[0]["msg"]})
    except HTTPException as e:
        return await _send(ws, {"type": "error", "detail": e.detail})
    await _send(ws, {"type": "lost_saved", "moment": moment, "created": created})
    if created:
        students = await run_in_threadpool(_lost_count, room.lecture_id, moment["slide_number"])
        hidden = students < HEATMAP_MIN_STUDENTS
        await _broadcast(room, {
            "type": "lost_count",
            "slide_number": moment["slide_number"],
            "students": None if hidden else students,
            "hidden": hidden,
        }, lecturers_only=True)


@router.websocket("/ws/lectures/{lecture_id}")
async def lecture_socket(ws: WebSocket, lecture_id: str, role: str = "student", student_id: str | None = None,
                         token: str | None = None):
    if role not in ("student", "lecturer") or (role == "student" and not (student_id and len(student_id) <= 64)):
        await ws.close(code=1008, reason="role must be lecturer, or student with a student_id")
        return
    if role == "lecturer":
        # Only staff can move the room's slides or broadcast captions.
        user = await run_in_threadpool(user_for_token, token)
        if user is None or user["role"] not in STAFF:
            await ws.close(code=1008, reason="lecturer needs a staff login token")
            return
    if len(lecture_id) > 64:
        await ws.close(code=1008, reason="lecture_id too long")
        return
    await ws.accept()
    room = _room(lecture_id)
    if role == "lecturer":
        room.lecturers.add(ws)
    else:
        await run_in_threadpool(_record_attendance, lecture_id, student_id)
        room.students[ws] = student_id
    log.info("join lecture=%s role=%s online=%d", lecture_id, role, room.online())
    await _broadcast(room, await _state(room))
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_MESSAGE_CHARS * 2:
                await _send(ws, {"type": "error", "detail": "Message too large"})
                continue
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError
            except ValueError:
                await _send(ws, {"type": "error", "detail": "Messages must be JSON objects"})
                continue
            if msg.get("type") == "ping":
                await _send(ws, {"type": "pong"})
            elif role == "lecturer":
                await _handle_lecturer(room, ws, msg)
            else:
                await _handle_student(room, ws, student_id, msg)
    except WebSocketDisconnect:
        pass
    finally:
        room.lecturers.discard(ws)
        room.students.pop(ws, None)
        log.info("leave lecture=%s role=%s online=%d", lecture_id, role, room.online())
        if not room.lecturers and not room.students:
            rooms.pop(lecture_id, None)
        else:
            await _broadcast(room, await _state(room))
