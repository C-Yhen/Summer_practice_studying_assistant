from fastapi.testclient import TestClient

from backend.app.models import Document


def _course(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"name": name, "code": name[:20]},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _document(
    client: TestClient,
    headers: dict[str, str],
    course_id: int,
    filename: str,
    content: bytes,
) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=headers,
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 201
    document = response.json()["data"]["document"]
    assert document["status"] == "ready"
    return document


def _second_user(client: TestClient) -> dict[str, str]:
    email = "rag-second@example.com"
    password = "rag-second-password"
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "RAG Second"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def test_persistent_rag_session_title_history_and_citations(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "RAG persistence")
    document = _document(
        client,
        auth_headers,
        course_id,
        "zephyr-protocol.txt",
        b"The Zephyr protocol uses cobalt lanterns for checksum recovery.",
    )

    created = client.post(
        f"/api/v1/courses/{course_id}/chat-sessions",
        headers=auth_headers,
        json={"mode": "strict", "document_ids": [document["id"], document["id"]]},
    )
    assert created.status_code == 201
    created_session = created.json()["data"]
    session_id = created_session["session_id"]
    assert created_session["title"] == "新对话"
    assert created_session["document_ids"] == [document["id"]]

    initial_list = client.get(
        f"/api/v1/courses/{course_id}/chat-sessions", headers=auth_headers
    )
    assert initial_list.status_code == 200
    assert initial_list.json()["data"]["total"] == 1
    assert initial_list.json()["data"]["items"][0]["session_id"] == session_id

    question = "What does the Zephyr protocol use for checksum recovery?"
    answered = client.post(
        f"/api/v1/chat-sessions/{session_id}/messages",
        headers=auth_headers,
        json={"question": question, "top_k": 3},
    )
    assert answered.status_code == 200
    answer = answered.json()["data"]
    assert answer["sufficient_evidence"] is True
    assert "cobalt lanterns" in answer["answer"]
    assert answer["citations"]
    citation = answer["citations"][0]
    assert citation["source_id"] == "S1"
    assert citation["document_id"] == document["id"]
    assert citation["document_name"] == "zephyr-protocol.txt"
    assert "cobalt lanterns" in citation["quote"]

    updated_list = client.get(
        f"/api/v1/courses/{course_id}/chat-sessions", headers=auth_headers
    ).json()["data"]["items"]
    assert updated_list[0]["title"] == question[:50]
    assert updated_list[0]["updated_at"] >= updated_list[0]["created_at"]

    history = client.get(
        f"/api/v1/chat-sessions/{session_id}/messages", headers=auth_headers
    )
    assert history.status_code == 200
    messages = history.json()["data"]["items"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["sufficient_evidence"] is None
    assert messages[1]["sufficient_evidence"] is True
    assert messages[1]["citations"][0]["document_id"] == document["id"]

    citation_response = client.get(
        f"/api/v1/chat-messages/{answer['message_id']}/citations",
        headers=auth_headers,
    )
    assert citation_response.status_code == 200
    assert citation_response.json()["data"]["items"] == answer["citations"]

    insufficient = client.post(
        f"/api/v1/chat-sessions/{session_id}/messages",
        headers=auth_headers,
        json={"question": "Explain photosynthesis quantum yield", "top_k": 3},
    )
    assert insufficient.status_code == 200
    insufficient_data = insufficient.json()["data"]
    assert insufficient_data["sufficient_evidence"] is False
    assert insufficient_data["citations"] == []
    assert "没有找到足够证据" in insufficient_data["answer"]
    refreshed_history = client.get(
        f"/api/v1/chat-sessions/{session_id}/messages", headers=auth_headers
    ).json()["data"]["items"]
    assert [message["role"] for message in refreshed_history] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_rag_document_scope_and_ready_validation(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "RAG scope")
    alpha = _document(
        client,
        auth_headers,
        course_id,
        "alpha.txt",
        b"alpha_scope_marker belongs to the silver compass chapter.",
    )
    beta = _document(
        client,
        auth_headers,
        course_id,
        "beta.txt",
        b"beta_scope_marker belongs to the amber telescope chapter.",
    )
    session = client.post(
        f"/api/v1/courses/{course_id}/chat-sessions",
        headers=auth_headers,
        json={"document_ids": [alpha["id"]]},
    ).json()["data"]

    alpha_answer = client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        headers=auth_headers,
        json={"question": "Where does alpha_scope_marker belong?"},
    ).json()["data"]
    assert alpha_answer["sufficient_evidence"] is True
    assert {item["document_id"] for item in alpha_answer["citations"]} == {alpha["id"]}

    beta_outside_scope = client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        headers=auth_headers,
        json={"question": "Where does beta_scope_marker belong?"},
    ).json()["data"]
    assert beta_outside_scope["sufficient_evidence"] is False
    assert beta_outside_scope["citations"] == []

    beta_selected = client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        headers=auth_headers,
        json={"question": "Where does beta_scope_marker belong?", "document_ids": [beta["id"]]},
    ).json()["data"]
    assert beta_selected["sufficient_evidence"] is True
    assert {item["document_id"] for item in beta_selected["citations"]} == {beta["id"]}

    with client.app.state.database.session_factory() as db:
        pending = Document(
            course_id=course_id,
            title="pending.txt",
            file_type="txt",
            file_path="/tmp/pending.txt",
            status="uploaded",
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)
        pending_id = pending.id

    not_ready = client.post(
        f"/api/v1/courses/{course_id}/chat-sessions",
        headers=auth_headers,
        json={"document_ids": [pending_id]},
    )
    assert not_ready.status_code == 409
    assert not_ready.json()["detail"] == "DOCUMENT_NOT_READY"

    other_course_id = _course(client, auth_headers, "RAG other course")
    other_document = _document(
        client,
        auth_headers,
        other_course_id,
        "other.txt",
        b"other_course_marker is isolated.",
    )
    invalid_scope = client.post(
        f"/api/v1/courses/{course_id}/chat-sessions",
        headers=auth_headers,
        json={"document_ids": [other_document["id"]]},
    )
    assert invalid_scope.status_code == 400
    assert invalid_scope.json()["detail"] == "DOCUMENT_SCOPE_INVALID"


def test_rag_session_authorization_and_schema_boundaries(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "RAG authorization")
    document = _document(
        client,
        auth_headers,
        course_id,
        "private-rag.txt",
        b"private_rag_marker belongs only to the owner.",
    )
    session = client.post(
        f"/api/v1/courses/{course_id}/chat-sessions",
        headers=auth_headers,
        json={"document_ids": [document["id"]]},
    ).json()["data"]
    answer = client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        headers=auth_headers,
        json={"question": "Who owns private_rag_marker?"},
    ).json()["data"]

    assert client.post(
        f"/api/v1/courses/{course_id}/chat-sessions", json={}
    ).status_code == 401
    assert client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        json={"question": "unauthorized"},
    ).status_code == 401

    second_headers = _second_user(client)
    assert client.get(
        f"/api/v1/courses/{course_id}/chat-sessions", headers=second_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/chat-sessions/{session['session_id']}/messages", headers=second_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/chat-messages/{answer['message_id']}/citations", headers=second_headers
    ).status_code == 404
    assert client.post(
        "/api/v1/chat-sessions/missing-session/messages",
        headers=auth_headers,
        json={"question": "missing"},
    ).status_code == 404
    assert client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        headers=auth_headers,
        json={"question": "   "},
    ).status_code == 422
    assert client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        headers=auth_headers,
        json={"question": "x" * 4001},
    ).status_code == 422


def test_provider_failure_does_not_persist_fake_answer(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    course_id = _course(client, auth_headers, "RAG provider failure")
    document = _document(
        client,
        auth_headers,
        course_id,
        "provider.txt",
        b"provider_failure_marker ensures retrieval has a real text chunk.",
    )
    session = client.post(
        f"/api/v1/courses/{course_id}/chat-sessions",
        headers=auth_headers,
        json={"document_ids": [document["id"]]},
    ).json()["data"]

    class FailingProvider:
        async def embed(self, _texts):
            raise RuntimeError("secret provider detail must not escape")

        async def chat(self, _messages, **_kwargs):
            raise RuntimeError("secret provider detail must not escape")

    monkeypatch.setattr(
        "backend.app.api.v1.rag.get_llm_provider",
        lambda _settings: FailingProvider(),
    )
    failed = client.post(
        f"/api/v1/chat-sessions/{session['session_id']}/messages",
        headers=auth_headers,
        json={"question": "Explain provider_failure_marker"},
    )
    assert failed.status_code == 503
    assert failed.json() == {"detail": "RAG_PROVIDER_UNAVAILABLE"}

    history = client.get(
        f"/api/v1/chat-sessions/{session['session_id']}/messages", headers=auth_headers
    ).json()["data"]["items"]
    assert history == []
    listed = client.get(
        f"/api/v1/courses/{course_id}/chat-sessions", headers=auth_headers
    ).json()["data"]["items"]
    assert listed[0]["title"] == "新对话"
