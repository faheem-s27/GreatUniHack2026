"""ElevenLabs tokens are issued only by the backend, without leaking the API key."""

import httpx
import pytest
from fastapi.testclient import TestClient

import captions
from main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOSTPOINT_DB", str(tmp_path / "test.db"))
    monkeypatch.setattr(captions, "SPEAKER_KEY", "lecturer-only")
    with TestClient(app) as test_client:
        yield test_client


def test_scribe_token_requires_lecturer_key_and_configuration(client, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret-key")
    assert client.post("/api/captions/scribe-token").status_code == 403
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    response = client.post("/api/captions/scribe-token", headers={"X-Speaker-Key": "lecturer-only"})
    assert response.status_code == 503
    assert "ELEVENLABS_API_KEY" in response.json()["detail"]


def test_scribe_token_uses_server_key_and_returns_only_temporary_token(client, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret-key")
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={"token": "one-time-token"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(captions.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(reply), **kwargs
    ))
    response = client.post("/api/captions/scribe-token", headers={"X-Speaker-Key": "lecturer-only"})
    assert response.status_code == 200
    assert response.json() == {"token": "one-time-token"}
    assert response.headers["cache-control"] == "no-store"
    assert str(requests[0].url) == captions.SCRIBE_TOKEN_URL
    assert requests[0].headers["xi-api-key"] == "secret-key"
    assert "secret-key" not in response.text


def test_scribe_token_hides_upstream_error(client, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "secret-key")
    original_client = httpx.AsyncClient
    monkeypatch.setattr(captions.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, text="secret-key invalid")), **kwargs
    ))
    response = client.post("/api/captions/scribe-token", headers={"X-Speaker-Key": "lecturer-only"})
    assert response.status_code == 502
    assert "secret-key" not in response.text
