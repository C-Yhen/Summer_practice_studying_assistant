from fastapi.testclient import TestClient


def _course(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"name": "Database Systems", "code": "DB101"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def test_document_rag_and_citations(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers)
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={
            "file": (
                "normal-forms.txt",
                b"Third normal form (3NF) removes transitive dependencies. "
                b"Every non-key attribute should depend directly on a candidate key.",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201
    document = uploaded.json()["data"]["document"]
    assert document["status"] == "ready"

    session = client.post(
        f"/api/v1/courses/{course_id}/chat-sessions",
        headers=auth_headers,
        json={"title": "3NF review", "mode": "strict", "document_ids": [document["id"]]},
    )
    assert session.status_code == 201
    session_id = session.json()["data"]["session_id"]
    answer = client.post(
        f"/api/v1/chat-sessions/{session_id}/messages",
        headers=auth_headers,
        json={"question": "What does third normal form remove?", "top_k": 3},
    )
    assert answer.status_code == 200
    data = answer.json()["data"]
    assert data["sufficient_evidence"] is True
    assert data["citations"]
    citation = data["citations"][0]
    assert citation["document_id"] == document["id"]
    assert citation["document_version"] == 1
    assert "Third normal form" in citation["quote"]

    reparsed = client.post(
        f"/api/v1/documents/{document['id']}/reparse", headers=auth_headers
    )
    assert reparsed.status_code == 200
    assert reparsed.json()["data"]["version"] == 2
    versions = client.get(
        f"/api/v1/documents/{document['id']}/versions", headers=auth_headers
    ).json()["data"]["items"]
    assert [item["version"] for item in versions] == [2, 1]
    assert versions[0]["is_current"] is True
    assert versions[1]["is_current"] is False

    refused = client.post(
        f"/api/v1/chat-sessions/{session_id}/messages",
        headers=auth_headers,
        json={"question": "Explain photosynthesis quantum yield", "top_k": 3},
    )
    assert refused.status_code == 200
    assert refused.json()["data"]["sufficient_evidence"] is False
    assert refused.json()["data"]["citations"] == []


def test_plan_confirmation_mastery_and_recommendations(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers)
    client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("db.txt", b"Database keys and normalization review.", "text/plain")},
    )
    generated = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=auth_headers,
        json={
            "start_date": "2026-07-14",
            "end_date": "2026-07-20",
            "daily_availability": {"default_minutes": 120},
            "session_minutes": 45,
            "goal": "Prepare for the database exam",
        },
    )
    assert generated.status_code == 200
    generated_data = generated.json()["data"]
    tasks = generated_data["candidate_version"]["tasks"]
    assert tasks
    confirmed = client.post(
        f"/api/v1/study-plans/{generated_data['plan_id']}/versions/1/confirm",
        headers=auth_headers,
        json={
            "expected_base_version": 0,
            "confirmation_token": generated_data["confirmation_token"],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["active_version"] == 1

    completed = client.post(
        f"/api/v1/study-tasks/{tasks[0]['id']}/complete",
        headers=auth_headers,
        json={"actual_minutes": 40},
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["mastery_score"] > 0.3

    mastery = client.get(
        f"/api/v1/courses/{course_id}/knowledge-mastery", headers=auth_headers
    )
    assert any(item["score"] > 0.3 for item in mastery.json()["data"]["items"])

    resources = client.get(
        f"/api/v1/courses/{course_id}/recommendations/resources", headers=auth_headers
    ).json()["data"]["items"]
    assert resources
    assert resources[0]["item_type"] == "course_chat"
    assert resources[0]["score_breakdown"]
    assert resources[0]["reason"]
