"""Tests for the live lecture WebSocket, the richer heatmap and course insights."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import login_staff


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    from main import app
    import live

    live.rooms.clear()
    with TestClient(app) as c:
        login_staff(c)
        import seed_demo
        from db import connect

        with connect() as conn:
            seed_demo.seed_course(conn, datetime.now(timezone.utc).isoformat())
        yield c


def lecturer_url(client):
    token = client.headers["Authorization"].removeprefix("Bearer ")
    return f"/ws/lectures/calc-w3?role=lecturer&token={token}"


def receive_until(ws, kind, **match):
    for _ in range(20):
        msg = ws.receive_json()
        if msg["type"] == kind and all(msg.get(k) == v for k, v in match.items()):
            return msg
    raise AssertionError(f"no {kind} message matching {match}")


def test_lecturer_drives_slides_and_captions(client):
    with client.websocket_connect(lecturer_url(client)) as lecturer, \
         client.websocket_connect("/ws/lectures/calc-w3?role=student&student_id=s1") as student:
        # An earlier broadcast may arrive first; the student's own join announces attendance 1.
        assert receive_until(student, "state", attendance=1, online=1)
        lecturer.send_json({"type": "slide", "slide_number": 2})
        assert receive_until(student, "slide")["slide_number"] == 2
        lecturer.send_json({"type": "caption", "text": "partial derivatives hold y constant", "lang": "en"})
        cap = receive_until(student, "caption")
        assert cap["text"].startswith("partial") and cap["slide_number"] == 2
        assert client.get("/api/lectures/calc-w3/live").json()["online"] == 1


def test_student_tap_saves_on_current_slide_and_lecturer_sees_count(client):
    with client.websocket_connect(lecturer_url(client)) as lecturer:
        lecturer.send_json({"type": "start"})
        lecturer.send_json({"type": "slide", "slide_number": 3})
        receive_until(lecturer, "slide", slide_number=3)  # the server has moved the room
        for i in range(5):
            with client.websocket_connect(f"/ws/lectures/calc-w3?role=student&student_id=s{i}") as student:
                receive_until(student, "state")
                student.send_json({"type": "lost", "topic": "Holding variables constant"})
                saved = receive_until(student, "lost_saved")
                assert saved["created"] and saved["moment"]["slide_number"] == 3
                assert saved["moment"]["lecture_time_s"] is not None
                student.send_json({"type": "lost"})  # double tap
                assert receive_until(student, "lost_saved")["created"] is False
            count = receive_until(lecturer, "lost_count")
            assert count["slide_number"] == 3
            assert count["students"] == (None if i < 4 else 5)
    # Taps are ordinary lost moments, visible to the student and in the heatmap.
    assert client.get("/api/lost-moments", params={"student_id": "s0"}).json()[0]["slide_number"] == 3
    heat = client.get("/api/lectures/calc-w3/heatmap").json()
    assert heat["attendance"] == 5 and heat["most_lost_slide"] == 3
    slide3 = next(s for s in heat["slides"] if s["slide_number"] == 3)
    assert slide3["percent_of_room"] == 100 and slide3["title"] == "A closer look"


def test_bad_messages_get_errors_not_disconnects(client):
    with client.websocket_connect("/ws/lectures/calc-w3?role=student&student_id=s1") as student:
        receive_until(student, "state")
        student.send_text("not json")
        assert receive_until(student, "error")
        student.send_json({"type": "slide", "slide_number": 9})  # students cannot move slides
        assert receive_until(student, "error")
        student.send_json({"type": "ping"})
        assert receive_until(student, "pong")
    with client.websocket_connect(lecturer_url(client)) as lecturer:
        receive_until(lecturer, "state")
        lecturer.send_json({"type": "slide", "slide_number": "two"})
        assert receive_until(lecturer, "error")


def test_student_needs_an_id(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/lectures/calc-w3?role=student") as ws:
            ws.receive_json()


def test_course_insights_respect_privacy(client):
    for i in range(6):
        client.post("/api/lost-moments", json={"student_id": f"s{i}", "lecture_id": "calc-w3", "slide_number": 2})
        client.post("/api/gaps", json={"student_id": f"s{i}", "course_id": "calc101", "concept": "Partial derivatives"})
    client.post("/api/gaps", json={"student_id": "s0", "course_id": "calc101", "concept": "Chain rule"})
    data = client.get("/api/courses/calc101/insights").json()
    w3 = next(l for l in data["lectures"] if l["lecture_id"] == "calc-w3")
    assert w3["students_lost"] == 6 and w3["most_lost_slide"] == 2
    assert data["most_lost_slides"][0]["citation"] == "Week 3, slide 2"
    assert [c["concept"] for c in data["struggling_concepts"]] == ["Partial derivatives"]  # chain rule: 1 student, hidden
    assert client.get("/api/courses/nope/insights").status_code == 404
