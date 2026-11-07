"""Tests for the tutor handoff (supervisor), the event log and the success metrics."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    from main import app

    with TestClient(app) as c:
        import seed_demo
        from db import connect

        with connect() as conn:
            seed_demo.seed_course(conn, datetime.now(timezone.utc).isoformat())
        yield c


def tap(client, student="s1", slide=2, lecture="calc-w3"):
    return client.post("/api/lost-moments", json={"student_id": student, "lecture_id": lecture, "slide_number": slide}).json()


def gap(client, concept="Partial derivatives", student="s1", moment=None):
    return client.post("/api/gaps", json={"student_id": student, "course_id": "calc101", "concept": concept,
                                          "lecture_id": "calc-w3", "slide_number": 2, "lost_moment_id": moment}).json()


def test_lost_three_times_on_same_idea_hands_off_to_tutor(client):
    assert gap(client, moment=tap(client, slide=2)["id"])["handoff"] is None
    assert gap(client, moment=tap(client, slide=3)["id"])["handoff"] is None
    third = gap(client, moment=tap(client, lecture="calc-w2", slide=9)["id"])
    assert third["times_lost"] == 3 and third["handoff"]["reason"] == "repeatedly_lost"
    # Only one open handoff per gap.
    assert gap(client, moment=tap(client, slide=1)["id"])["handoff"] is None

    queue = client.get("/api/courses/calc101/handoffs").json()
    assert len(queue) == 1 and queue[0]["status"] == "open"
    item = queue[0]
    assert item["gap"]["concept"] == "Partial derivatives" and item["gap"]["slide"]["citation"] == "Week 3, slide 2"
    assert item["student"].startswith("student-") and "student_id" not in item
    assert item["transcript"] is None


def test_many_attempts_in_coach_hand_off_and_response_says_so(client):
    s = client.post("/api/coach/sessions", json={"student_id": "s1", "course_id": "calc101",
                                                 "concept": "Chain rule", "question": "how does the chain rule work"}).json()
    handoffs = []
    for i in range(6):
        r = client.post(f"/api/coach/sessions/{s['id']}/messages",
                        json={"student_id": "s1", "role": "student", "content": f"try {i}", "is_attempt": True}).json()
        handoffs.append(r["handoff"])
    assert handoffs[:5] == [None] * 5 and handoffs[5]["reason"] == "many_attempts"
    assert handoffs[5]["session_id"] == s["id"]


def test_student_request_shares_transcript_only_when_asked(client):
    s = client.post("/api/coach/sessions", json={"student_id": "s1", "course_id": "calc101", "concept": "Limits"}).json()
    client.post(f"/api/coach/sessions/{s['id']}/messages", json={"student_id": "s1", "role": "student", "content": "I'm stuck on limits"})
    private = client.post("/api/handoffs", json={"student_id": "s1", "course_id": "calc101", "session_id": s["id"]}).json()
    shared = client.post("/api/handoffs", json={"student_id": "s1", "course_id": "calc101", "session_id": s["id"],
                                                "share_transcript": True, "note": "can we go through this?"}).json()
    assert client.get(f"/api/handoffs/{private['id']}").json()["transcript"] is None
    transcript = client.get(f"/api/handoffs/{shared['id']}").json()["transcript"]
    assert transcript[0]["content"] == "I'm stuck on limits"
    # Another student's session cannot be attached.
    assert client.post("/api/handoffs", json={"student_id": "s2", "course_id": "calc101", "session_id": s["id"]}).status_code == 404


def test_tutor_claims_and_resolves(client):
    h = client.post("/api/handoffs", json={"student_id": "s1", "course_id": "calc101", "note": "help"}).json()
    r = client.patch(f"/api/handoffs/{h['id']}", json={"status": "claimed", "tutor": "Dr T"}).json()
    assert r["status"] == "claimed" and r["claimed_at"]
    r = client.patch(f"/api/handoffs/{h['id']}", json={"status": "resolved", "tutor": "Dr T", "note": "Office hours Tue 2pm"}).json()
    assert r["status"] == "resolved" and r["tutor_note"] == "Office hours Tue 2pm"
    assert client.patch(f"/api/handoffs/{h['id']}", json={"status": "claimed", "tutor": "X"}).status_code == 409
    mine = client.get("/api/handoffs", params={"student_id": "s1"}).json()
    assert mine[0]["tutor_note"] == "Office hours Tue 2pm"
    assert client.get("/api/handoffs", params={"student_id": "s2"}).json() == []


def test_every_step_is_logged_in_the_student_timeline(client):
    m = tap(client)
    tap(client)  # double tap: deduplicated, not logged again
    s = client.post("/api/coach/sessions", json={"student_id": "s1", "course_id": "calc101", "lost_moment_id": m["id"],
                                                 "concept": "Partial derivatives"}).json()
    for i in range(3):
        client.post(f"/api/coach/sessions/{s['id']}/messages", json={"student_id": "s1", "role": "student", "content": str(i), "is_attempt": True})
    client.patch(f"/api/coach/sessions/{s['id']}", json={"student_id": "s1", "status": "resolved"})
    kinds = [e["kind"] for e in reversed(client.get("/api/events", params={"student_id": "s1"}).json())]
    assert kinds == ["lost_tap", "gap_recorded", "coach_session", "coach_attempt", "coach_attempt", "coach_attempt",
                     "coach_mode", "coach_resolved", "gap_closed"]
    mode = client.get("/api/events", params={"student_id": "s1", "kind": "coach_mode"}).json()[0]
    assert mode["detail"] == {"from": "guide", "to": "explain", "reason": "attempts"}
    assert client.get("/api/events", params={"student_id": "s2"}).json() == []


def test_metrics_match_the_brief(client):
    # s1: lost twice on one idea, coached, resolved, then lost again (reopened).
    g = gap(client, moment=tap(client, slide=2)["id"])
    gap(client, moment=tap(client, slide=3)["id"])
    s = client.post("/api/coach/sessions", json={"student_id": "s1", "course_id": "calc101", "concept": "Partial derivatives"}).json()
    client.post(f"/api/coach/sessions/{s['id']}/messages", json={"student_id": "s1", "role": "student", "content": "x", "is_attempt": True})
    client.patch(f"/api/coach/sessions/{s['id']}", json={"student_id": "s1", "status": "resolved"})
    gap(client, moment=tap(client, slide=1)["id"])
    # s2: lost once, never coached.
    gap(client, student="s2", moment=tap(client, student="s2")["id"])
    client.post("/api/lectures/calc-w3/slides/2/recap", json={"note": "5 minute recap"})

    m = client.get("/api/courses/calc101/metrics").json()
    assert m["lost_moments"] == {"total": 4, "students": 2}
    assert m["gaps"]["repeat_lost_rate"] == 0.5  # s1 repeated, s2 did not
    assert m["gaps"]["closed_then_reopened"] == 1
    assert m["coach"]["resolved"] == 1 and m["coach"]["avg_attempts_to_resolve"] == 1
    assert m["handoffs"]["by_reason"] == {"repeatedly_lost": 1} and g["handoff"] is None
    assert m["lecturer_actions"]["slides_recapped"] == 1
    week = m["repeat_lost_by_week"][0]
    assert (week["first_time"], week["repeat"]) == (2, 2)
    assert client.post("/api/lectures/nope/slides/1/recap").status_code == 404
