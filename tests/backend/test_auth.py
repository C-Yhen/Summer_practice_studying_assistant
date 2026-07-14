from fastapi.testclient import TestClient


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_register_login_and_me(client: TestClient) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Alice@Example.COM",
            "password": "a-secure-password",
            "full_name": "Alice",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["data"]["email"] == "alice@example.com"
    assert "password_hash" not in registration.json()["data"]

    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "another-password",
            "full_name": "Other",
        },
    )
    assert duplicate.status_code == 409

    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "a-secure-password"},
    )
    assert login.status_code == 200
    body = login.json()["data"]
    assert body["token_type"] == "bearer"
    me = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["data"]["display_name"] == "Alice"


def test_me_requires_valid_token(client: TestClient) -> None:
    assert client.get("/api/v1/users/me").status_code == 401
    assert (
        client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer not-a-token"}
        ).status_code
        == 401
    )
