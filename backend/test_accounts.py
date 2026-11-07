"""Tests for accounts, staff-only routes, error shape, health and serving the built frontend."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import STAFF_CODE, login_staff


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    import accounts
    from main import app

    accounts._failed.clear()
    with TestClient(app) as c:
        yield c


def register(client, email="amira@student.ac.uk", password="partial derivs", **extra):
    return client.post("/api/auth/register", json={"email": email, "name": "Amira", "password": password, **extra})


def test_student_registers_logs_in_and_out(client):
    r = register(client)
    assert r.status_code == 201 and r.json()["user"]["role"] == "student"
    assert register(client, email="AMIRA@student.ac.uk").status_code == 409  # emails are case-insensitive
    token = client.post("/api/auth/login", json={"email": "Amira@Student.ac.uk", "password": "partial derivs"}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=auth).json()["email"] == "amira@student.ac.uk"
    assert client.post("/api/auth/logout", headers=auth).status_code == 204
    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_passwords_and_tokens_are_not_stored_in_plain_text(client):
    token = register(client).json()["token"]
    from db import connect

    with connect() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
        sessions = [r[0] for r in conn.execute("SELECT token_hash FROM auth_sessions")]
    assert "partial derivs" not in stored and stored.startswith("scrypt$")
    assert token not in sessions


def test_staff_registration_needs_the_staff_code(client):
    assert register(client, role="lecturer").status_code == 403
    assert register(client, role="lecturer", staff_code="guess").status_code == 403
    assert register(client, role="tutor", staff_code=STAFF_CODE).json()["user"]["role"] == "tutor"


def test_repeated_wrong_passwords_are_refused_for_a_while(client):
    register(client)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "amira@student.ac.uk", "password": "wrong guess"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "amira@student.ac.uk", "password": "partial derivs"})
    assert r.status_code == 429


def test_staff_routes_need_a_staff_login(client):
    staff_calls = [
        ("post", "/api/courses", {"id": "c1", "title": "C"}),
        ("get", "/api/courses/c1/coursework", None),
        ("get", "/api/courses/c1/metrics", None),
        ("get", "/api/courses/c1/handoffs", None),
        ("post", "/api/lectures/l1/pdf", None),
    ]
    for method, url, body in staff_calls:
        r = getattr(client, method)(url, **({"json": body} if body else {}))
        assert r.status_code == 401, url
        assert r.json() == {"detail": "Please log in", "status": 401}
    student = register(client).json()["token"]
    assert client.post("/api/courses", json={"id": "c1", "title": "C"},
                       headers={"Authorization": f"Bearer {student}"}).status_code == 403
    login_staff(client)
    assert client.post("/api/courses", json={"id": "c1", "title": "C"}).status_code == 201


def test_student_routes_still_work_without_a_login(client):
    r = client.post("/api/lost-moments", json={"student_id": "s1", "lecture_id": "calc-w3", "slide_number": 2})
    assert r.status_code == 201
    assert client.get("/api/lectures/calc-w3/heatmap").status_code == 200
    assert client.get("/api/courses").status_code == 200
    assert client.post("/api/coursework/check", json={"course_id": "c", "text": "hi"}).status_code == 200


def test_lecturer_socket_needs_a_staff_token(client):
    student = register(client).json()["token"]
    for url in ["/ws/lectures/l1?role=lecturer", f"/ws/lectures/l1?role=lecturer&token={student}"]:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(url) as ws:
                ws.receive_json()
    token = login_staff(client)
    with client.websocket_connect(f"/ws/lectures/l1?role=lecturer&token={token}") as ws:
        assert ws.receive_json()["type"] == "state"


def test_errors_have_one_shape(client):
    r = client.post("/api/lost-moments", json={"student_id": "s1", "lecture_id": "calc-w3", "slide_number": 0})
    body = r.json()
    assert r.status_code == 422 and body["status"] == 422
    assert body["detail"].startswith("slide_number:") and body["errors"][0]["field"] == "slide_number"
    assert client.get("/api/courses/nope").json() == {"detail": "Course not found", "status": 404}


def test_health_checks_the_database(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["database"] is True and body["version"]


def test_serves_built_frontend_with_fallback(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>LostPoint</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("not public")
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("LOSTPOINT_STATIC_DIR", str(dist))
    import importlib

    import main

    importlib.reload(main)
    try:
        with TestClient(main.app) as c:
            assert c.get("/").text == "<html>LostPoint</html>"
            assert c.get("/assets/app.js").text == "console.log(1)"
            assert c.get("/insights").text == "<html>LostPoint</html>"  # client-side route
            assert "not public" not in c.get("/../secret.txt").text
            assert c.get("/api/nope").status_code == 404
            assert c.get("/api/health").json()["status"] == "ok"
    finally:
        monkeypatch.delenv("LOSTPOINT_STATIC_DIR")
        importlib.reload(main)
