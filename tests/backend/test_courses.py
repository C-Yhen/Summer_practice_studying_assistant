from fastapi.testclient import TestClient


def test_course_crud_and_exam_date(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/courses",
        headers=auth_headers,
        json={
            "name": "Machine Learning",
            "code": "ML101",
            "description": "Core concepts",
            "color": "#4466ee",
        },
    )
    assert created.status_code == 201
    course_id = created.json()["data"]["id"]

    listing = client.get("/api/v1/courses", headers=auth_headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["data"]["items"]] == [course_id]

    updated = client.patch(
        f"/api/v1/courses/{course_id}",
        headers=auth_headers,
        json={"name": "Applied Machine Learning", "archived": True},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "Applied Machine Learning"

    assert client.get("/api/v1/courses", headers=auth_headers).json()["data"]["items"] == []
    archived = client.get(
        "/api/v1/courses?include_archived=true", headers=auth_headers
    )
    assert len(archived.json()["data"]["items"]) == 1

    exam = client.put(
        f"/api/v1/courses/{course_id}/exam-date",
        headers=auth_headers,
        json={"exam_date": "2026-08-20"},
    )
    assert exam.status_code == 200
    assert exam.json()["data"]["exam_date"] == "2026-08-20"

    deleted = client.delete(f"/api/v1/courses/{course_id}", headers=auth_headers)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["status"] == "archived"
    assert client.get(f"/api/v1/courses/{course_id}", headers=auth_headers).status_code == 200


def test_course_isolation_between_users(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course = client.post(
        "/api/v1/courses", headers=auth_headers, json={"name": "Private Course"}
    ).json()["data"]
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "second@example.com",
            "password": "second-password",
            "full_name": "Second User",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "second@example.com", "password": "second-password"},
    ).json()["data"]
    second_headers = {"Authorization": f"Bearer {login['access_token']}"}
    assert (
        client.get(f"/api/v1/courses/{course['id']}", headers=second_headers).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/courses/{course['id']}",
            headers=second_headers,
            json={"name": "Stolen"},
        ).status_code
        == 404
    )
