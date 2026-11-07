"""Shared test setup: every test may register staff with this code."""

import pytest

STAFF_CODE = "test-staff-code"


@pytest.fixture(autouse=True)
def _staff_code(monkeypatch):
    monkeypatch.setenv("LOSTPOINT_STAFF_CODE", STAFF_CODE)


def login_staff(client, email="lecturer@test.ac.uk", role="lecturer") -> str:
    """Register a staff account and send its token with every request from this client."""
    r = client.post("/api/auth/register", json={"email": email, "name": "Dr Test", "password": "correct horse",
                                                "role": role, "staff_code": STAFF_CODE})
    token = r.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token
