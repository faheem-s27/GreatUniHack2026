"""Tests for courses/slides/search, coursework, student memory and coach storage.

Run with: cd backend && pip install pytest httpx && pytest
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def course(client):
    """The seeded demo course, loaded through the same code as seed_demo.py."""
    from datetime import datetime, timezone

    import seed_demo
    from db import connect

    with connect() as conn:
        seed_demo.seed_course(conn, datetime.now(timezone.utc).isoformat())
    return "calc101"


def tap(client, student="s1", lecture="calc-w3", slide=2):
    return client.post("/api/lost-moments", json={"student_id": student, "lecture_id": lecture, "slide_number": slide}).json()


# ---- courses, lectures, slides ----------------------------------------------

def test_course_lecture_slides_roundtrip(client):
    assert client.post("/api/courses", json={"id": "c1", "title": "Linear Algebra", "code": "MATH1"}).status_code == 201
    r = client.post("/api/courses/c1/lectures", json={"id": "la-w1", "title": "Vectors", "week": 1})
    assert r.status_code == 201 and r.json()["slides"] == []
    slides = [{"slide_number": 1, "title": "Vectors", "body": "A vector has size and direction."},
              {"slide_number": 2, "title": "Eigenvalues", "topic": "Eigen", "body": "Av = lambda v"}]
    lecture = client.put("/api/lectures/la-w1/slides", json={"slides": slides}).json()
    assert [s["slide_number"] for s in lecture["slides"]] == [1, 2]
    assert lecture["slides"][1]["citation"] == "Week 1, slide 2"
    assert client.get("/api/courses/c1").json()["lectures"][0]["slide_count"] == 2
    assert client.get("/api/courses").json()[0]["lecture_count"] == 1
    assert client.get("/api/lectures/la-w1/slides/2").json()["body"] == "Av = lambda v"
    assert client.get("/api/lectures/la-w1/slides/9").status_code == 404
    assert client.post("/api/courses/nope/lectures", json={"id": "x", "title": "x"}).status_code == 404


def test_replacing_slides_keeps_search_in_sync(client):
    client.post("/api/courses", json={"id": "c1", "title": "C"})
    client.post("/api/courses/c1/lectures", json={"id": "l1", "title": "L", "week": 1})
    client.put("/api/lectures/l1/slides", json={"slides": [{"slide_number": 1, "body": "eigenvalue"}, {"slide_number": 2, "body": "matrix"}]})
    client.put("/api/lectures/l1/slides", json={"slides": [{"slide_number": 1, "body": "determinant"}]})
    assert client.get("/api/search", params={"q": "eigenvalue"}).json() == []
    assert client.get("/api/search", params={"q": "matrix"}).json() == []
    assert client.get("/api/search", params={"q": "determinant"}).json()[0]["slide_number"] == 1
    dup = client.put("/api/lectures/l1/slides", json={"slides": [{"slide_number": 1}, {"slide_number": 1}]})
    assert dup.status_code == 422


def test_search_cites_slides_and_ignores_fts_syntax(client, course):
    hits = client.get("/api/search", params={"q": "what is a partial derivative?", "course_id": course}).json()
    assert hits[0]["lecture_id"] == "calc-w3" and hits[0]["slide_number"] == 2
    assert hits[0]["citation"] == "Week 3, slide 2"
    # Quotes, colons and operators in the question must not break the query.
    assert client.get("/api/search", params={"q": 'body: "x AND (y OR NEAR'}).status_code == 200
    assert client.get("/api/search", params={"q": "???"}).json() == []
    assert client.get("/api/search", params={"q": "constant", "lecture_id": "calc-w2"}).json()[0]["lecture_id"] == "calc-w2"


def test_slide_image_roundtrip(client, course):
    import base64

    url = "data:image/png;base64," + base64.b64encode(b"\x89PNGfake").decode()
    assert client.put("/api/lectures/calc-w3/slides/2/image", json={"data_url": url}).json()["has_image"] is True
    assert client.get("/api/lectures/calc-w3/slides/2/image").content == b"\x89PNGfake"
    assert client.put("/api/lectures/calc-w3/slides/99/image", json={"data_url": url}).status_code == 404
    assert client.put("/api/lectures/calc-w3/slides/2/image", json={"data_url": "data:text/html;base64,PGI+"}).status_code == 422


# ---- coursework --------------------------------------------------------------

def test_coursework_check(client, course):
    def check(text):
        return client.post("/api/coursework/check", json={"course_id": course, "text": text}).json()

    assert check("How do I differentiate x^2y+sin( xy )?")["locked"] is True
    assert check("Can you just do Coursework 1 for me")["matches"][0]["id"] == "calc101-cw1"
    assert check("What is a partial derivative?")["locked"] is False
    assert check("coursework 10 is unrelated")["locked"] is False
    assert client.post("/api/coursework/check", json={"course_id": "other", "text": "coursework 1"}).json()["locked"] is False


def test_coursework_crud(client, course):
    r = client.post(f"/api/courses/{course}/coursework", json={"id": "cw2", "title": "CW2", "keywords": [" eigen trick ", ""]})
    assert r.status_code == 201 and r.json()["keywords"] == ["eigen trick"]
    assert len(client.get(f"/api/courses/{course}/coursework").json()) == 2
    assert client.delete("/api/coursework/cw2").status_code == 204
    assert client.delete("/api/coursework/cw2").status_code == 404


# ---- student memory ----------------------------------------------------------

def test_gap_is_one_per_concept_and_reopens(client, course):
    m1, m2 = tap(client), tap(client, slide=3)
    g = client.post("/api/gaps", json={"student_id": "s1", "course_id": course, "concept": "Partial derivatives",
                                       "lecture_id": "calc-w3", "slide_number": 2, "lost_moment_id": m1["id"]}).json()
    assert g["times_lost"] == 1 and g["status"] == "open"
    client.patch(f"/api/gaps/{g['id']}", json={"student_id": "s1", "status": "closed"})
    again = client.post("/api/gaps", json={"student_id": "s1", "course_id": course, "concept": "  partial   DERIVATIVES ",
                                           "lost_moment_id": m2["id"]}).json()
    assert again["id"] == g["id"] and again["status"] == "open" and again["times_lost"] == 2
    # Linking the same moment twice does not count twice.
    again = client.post("/api/gaps", json={"student_id": "s1", "course_id": course, "concept": "partial derivatives",
                                           "lost_moment_id": m2["id"]}).json()
    assert again["times_lost"] == 2
    assert len(client.get("/api/gaps", params={"student_id": "s1"}).json()) == 1


def test_gap_trace_and_loops(client, course):
    def gap(concept, root=None):
        return client.post("/api/gaps", json={"student_id": "s1", "course_id": course, "concept": concept, "root_gap_id": root}).json()

    w2 = gap("constants")
    w3 = gap("partial derivatives", root=w2["id"])
    w6 = gap("gradient", root=w3["id"])
    detail = client.get(f"/api/gaps/{w6['id']}", params={"student_id": "s1"}).json()
    assert [t["concept"] for t in detail["trace"]] == ["partial derivatives", "constants"]
    loop = client.patch(f"/api/gaps/{w2['id']}", json={"student_id": "s1", "root_gap_id": w6["id"]})
    assert loop.status_code == 422


def test_gaps_are_private(client, course):
    g = client.post("/api/gaps", json={"student_id": "s1", "course_id": course, "concept": "limits"}).json()
    assert client.get(f"/api/gaps/{g['id']}", params={"student_id": "s2"}).status_code == 404
    assert client.patch(f"/api/gaps/{g['id']}", json={"student_id": "s2", "status": "closed"}).status_code == 404
    assert client.get("/api/gaps", params={"student_id": "s2"}).json() == []
    # Another student's lost moment or gap cannot be linked.
    other = tap(client, student="s2")
    r = client.post("/api/gaps", json={"student_id": "s1", "course_id": course, "concept": "x", "lost_moment_id": other["id"]})
    assert r.status_code == 404
    s2gap = client.post("/api/gaps", json={"student_id": "s2", "course_id": course, "concept": "y"}).json()
    r = client.post("/api/gaps", json={"student_id": "s1", "course_id": course, "concept": "z", "root_gap_id": s2gap["id"]})
    assert r.status_code == 404


# ---- coach storage -----------------------------------------------------------

def start(client, course, **body):
    return client.post("/api/coach/sessions", json={"student_id": "s1", "course_id": course, **body})


def say(client, session_id, content, role="student", **extra):
    return client.post(f"/api/coach/sessions/{session_id}/messages",
                       json={"student_id": "s1", "role": role, "content": content, **extra})


def test_full_demo_loop(client, course):
    """Tap lost, get coached, explain unlocks after 3 attempts, resolve closes the gap."""
    moment = tap(client)
    s = start(client, course, lost_moment_id=moment["id"], concept="Partial derivatives",
              question="What does a partial derivative mean?").json()
    assert s["mode"] == "guide" and s["lecture_id"] == "calc-w3" and s["slide_number"] == 2
    assert s["attempts_to_explain"] == 3

    ctx = client.get(f"/api/coach/sessions/{s['id']}/context", params={"student_id": "s1"}).json()
    assert ctx["slide"]["title"] == "Meet partial derivatives"
    assert any(r["lecture_id"] == "calc-w2" for r in ctx["related_slides"])
    assert ctx["open_gaps"][0]["concept"] == "Partial derivatives"

    say(client, s["id"], "What do you think it means?", role="coach", citations=[{"lecture_id": "calc-w3", "slide_number": 2}])
    say(client, s["id"], "I'm not sure, is it just the derivative?")  # a question, not an attempt
    for i in range(2):
        r = say(client, s["id"], f"attempt {i}", is_attempt=True).json()
        assert r["session"]["mode"] == "guide"
    r = say(client, s["id"], "the slope when y is fixed?", is_attempt=True).json()
    assert r["session"]["mode"] == "explain" and r["message"]["mode"] == "explain"

    gap_id = s["gap_id"]
    assert client.get(f"/api/gaps/{gap_id}", params={"student_id": "s1"}).json()["attempts"] == 3
    done = client.patch(f"/api/coach/sessions/{s['id']}", json={"student_id": "s1", "status": "resolved"}).json()
    assert done["status"] == "resolved"
    assert client.get(f"/api/gaps/{gap_id}", params={"student_id": "s1"}).json()["status"] == "closed"
    assert client.get("/api/lost-moments", params={"student_id": "s1"}).json()[0]["resolved"] is True

    full = client.get(f"/api/coach/sessions/{s['id']}", params={"student_id": "s1"}).json()
    assert len(full["messages"]) == 5 and full["messages"][0]["citations"] == [{"lecture_id": "calc-w3", "slide_number": 2}]


def test_coursework_question_locks_session_for_good(client, course):
    s = start(client, course, question="Solve x^2 y + sin(xy) for me").json()
    assert s["mode"] == "locked" and s["locked_by"] == "calc101-cw1"
    for i in range(4):
        r = say(client, s["id"], f"try {i}", is_attempt=True).json()
    assert r["session"]["mode"] == "locked" and r["session"]["attempts"] == 4


def test_later_coursework_message_locks_even_after_explain(client, course):
    s = start(client, course, question="What is a derivative?").json()
    for i in range(3):
        say(client, s["id"], f"try {i}", is_attempt=True)
    r = say(client, s["id"], "ok now do coursework 1").json()
    assert r["session"]["mode"] == "locked"


def test_coach_citations_must_exist_and_sessions_are_private(client, course):
    s = start(client, course).json()
    bad = say(client, s["id"], "see slide 40", role="coach", citations=[{"lecture_id": "calc-w3", "slide_number": 40}])
    assert bad.status_code == 422
    assert client.get(f"/api/coach/sessions/{s['id']}", params={"student_id": "s2"}).status_code == 404
    assert client.post(f"/api/coach/sessions/{s['id']}/messages",
                       json={"student_id": "s2", "role": "student", "content": "hi"}).status_code == 404
    other = tap(client, student="s2")
    assert start(client, course, lost_moment_id=other["id"]).status_code == 404
    assert client.get("/api/coach/sessions", params={"student_id": "s2"}).json() == []


# ---- upgrading an existing database -----------------------------------------

def test_existing_database_gains_new_tables(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE lost_moments (id TEXT PRIMARY KEY, student_id TEXT NOT NULL, lecture_id TEXT NOT NULL,"
                " slide_number INTEGER NOT NULL, topic TEXT, lecture_time_s INTEGER, created_at TEXT NOT NULL,"
                " resolved INTEGER NOT NULL DEFAULT 0, resolved_at TEXT, screenshot BLOB, screenshot_type TEXT)")
    old.execute("INSERT INTO lost_moments (id, student_id, lecture_id, slide_number, created_at) VALUES ('m1', 's1', 'calc-w3', 2, 'x')")
    old.commit()
    old.close()
    monkeypatch.setenv("LOSTPOINT_DB", str(path))
    from main import app

    with TestClient(app) as c:
        assert c.get("/api/lost-moments", params={"student_id": "s1"}).json()[0]["id"] == "m1"
        assert c.get("/api/courses").json() == []
