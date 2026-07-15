from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.main import create_app


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(
        database_url="sqlite://",
        jwt_secret="test-secret-that-is-long-enough",
        auto_create_tables=True,
        cors_origins=[],
        sync_document_processing=True,
        upload_dir=tmp_path / "uploads",
    )
    database = Database(settings.database_url)
    app = create_app(settings=settings, database=database)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "learner@example.com",
            "password": "correct-horse-battery-staple",
            "full_name": "Test Learner",
        },
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
