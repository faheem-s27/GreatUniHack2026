"""Run with: cd backend && pip install pytest httpx && pytest"""

import base64

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    from main import app

    with TestClient(app) as c:
        yield c


def tap(client, student="s1", slide=14, **extra):
    return client.post("/api/lost-moments", json={"student_id": student, "lecture_id": "calc-w3", "slide_number": slide, **extra})


def test_tap_saves_moment(client):
    r = tap(client, topic="Partial derivatives", lecture_time_s=1380)
    assert r.status_code == 201
    m = r.json()
    assert m["slide_number"] == 14 and m["topic"] == "Partial derivatives" and m["resolved"] is False
    assert "student_id" not in m
    assert client.get("/api/lost-moments", params={"student_id": "s1"}).json()[0]["id"] == m["id"]


def test_double_tap_is_deduplicated(client):
    first = tap(client).json()
    second = tap(client)
    assert second.status_code == 200 and second.json()["id"] == first["id"]
    assert len(client.get("/api/lost-moments", params={"student_id": "s1"}).json()) == 1


def test_client_id_makes_offline_retry_idempotent(client):
    assert tap(client, id="offline-1").status_code == 201
    assert tap(client, id="offline-1").status_code == 200
    assert tap(client, student="s2", id="offline-1").status_code == 409


def test_students_only_see_and_change_their_own(client):
    m = tap(client).json()
    assert client.get("/api/lost-moments", params={"student_id": "s2"}).json() == []
    assert client.patch(f"/api/lost-moments/{m['id']}", json={"student_id": "s2", "resolved": True}).status_code == 404
    r = client.patch(f"/api/lost-moments/{m['id']}", json={"student_id": "s1", "resolved": True})
    assert r.json()["resolved"] is True and r.json()["resolved_at"]


def test_screenshot_roundtrip_and_validation(client):
    m = tap(client).json()
    png = b"\x89PNG\r\n\x1a\nfake"
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    r = client.put(f"/api/lost-moments/{m['id']}/screenshot", json={"student_id": "s1", "data_url": url})
    assert r.status_code == 200 and r.json()["has_screenshot"] is True
    got = client.get(f"/api/lost-moments/{m['id']}/screenshot", params={"student_id": "s1"})
    assert got.content == png and got.headers["content-type"] == "image/png"
    assert client.get(f"/api/lost-moments/{m['id']}/screenshot", params={"student_id": "s2"}).status_code == 404
    bad = client.put(f"/api/lost-moments/{m['id']}/screenshot", json={"student_id": "s1", "data_url": "data:text/html;base64,PGI+"})
    assert bad.status_code == 422


def test_heatmap_hides_slides_under_five_students(client):
    for i in range(5):
        tap(client, student=f"s{i}", slide=14)
    tap(client, student="s0", slide=14, id="repeat")  # repeat taps by one student count once
    tap(client, student="s9", slide=3)
    slides = {s["slide_number"]: s for s in client.get("/api/lectures/calc-w3/heatmap").json()["slides"]}
    assert (slides[14]["students"], slides[14]["hidden"]) == (5, False)
    assert (slides[3]["students"], slides[3]["hidden"], slides[3]["percent_of_room"]) == (None, True, None)
