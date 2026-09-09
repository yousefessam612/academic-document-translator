"""Site-wide password protection (APP_ACCESS_PASSWORD) tests."""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient


def basic_auth(password: str, username: str = "user") -> str:
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def protected(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_access_password", "secret123", raising=False)
    yield
    monkeypatch.setattr(settings, "app_access_password", "", raising=False)


class TestNoPassword:
    def test_open_access_by_default(self, client):
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/terminology").status_code == 200


class TestPasswordProtection:
    def test_api_requires_auth(self, client, protected):
        response = client.get("/api/terminology")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate", "").startswith("Basic")

    def test_correct_password_grants_access(self, client, protected):
        response = client.get("/api/terminology", headers={"Authorization": basic_auth("secret123")})
        assert response.status_code == 200

    def test_any_username_accepted(self, client, protected):
        response = client.get(
            "/api/terminology", headers={"Authorization": basic_auth("secret123", username="anything")}
        )
        assert response.status_code == 200

    def test_wrong_password_rejected(self, client, protected):
        response = client.get("/api/terminology", headers={"Authorization": basic_auth("wrong")})
        assert response.status_code == 401

    def test_malformed_header_rejected(self, client, protected):
        response = client.get("/api/terminology", headers={"Authorization": "Basic !!!notb64"})
        assert response.status_code == 401
        response = client.get("/api/terminology", headers={"Authorization": "Bearer token"})
        assert response.status_code == 401

    def test_health_probes_stay_public(self, client, protected):
        assert client.get("/api/health").status_code == 200
        assert client.get("/healthz").status_code == 200
        # trailing-slash variant must not be blocked by the password either
        assert client.get("/api/health/").status_code != 401

    def test_uploads_require_auth(self, client, protected):
        response = client.post(
            "/api/documents/upload",
            files={"file": ("x.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 401

    def test_protection_removed_when_password_cleared(self, client, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "app_access_password", "", raising=False)
        assert client.get("/api/terminology").status_code == 200
