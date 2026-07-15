from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import AsyncTask, Document, DocumentChunk, DocumentVersion


def _course(client: TestClient, headers: dict[str, str], name: str = "Round 03") -> int:
    response = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"name": name, "code": "R03"},
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _second_user(client: TestClient) -> dict[str, str]:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "document-second@example.com",
            "password": "second-user-password",
            "display_name": "Second User",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "document-second@example.com",
            "password": "second-user-password",
        },
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_document_upload_persists_file_records_chunks_and_task(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers)
    content = b"Round03 unique persistence marker. Normalization uses candidate keys."
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("round03-notes.md", content, "text/markdown")},
        data={"title": "Round 03 notes"},
    )
    assert uploaded.status_code == 201
    upload_data = uploaded.json()["data"]
    document_data = upload_data["document"]
    task_id = upload_data["async_task_id"]
    assert document_data["status"] == "ready"
    assert document_data["file_type"] == "md"
    assert task_id

    listed = client.get(f"/api/v1/courses/{course_id}/documents", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["id"] == document_data["id"]

    task_response = client.get(f"/api/v1/async-tasks/{task_id}", headers=auth_headers)
    assert task_response.status_code == 200
    task_data = task_response.json()["data"]
    assert task_data["status"] == "success"
    assert task_data["progress"] == 100
    assert task_data["result_data"]["chunk_count"] >= 1

    latest = client.get(
        f"/api/v1/documents/{document_data['id']}/tasks/latest",
        headers=auth_headers,
    )
    assert latest.status_code == 200
    assert latest.json()["data"]["task_id"] == task_id

    with client.app.state.database.session_factory() as db:
        document = db.get(Document, document_data["id"])
        task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id))
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_data["id"],
                DocumentVersion.version_no == 1,
            )
        )
        chunk_total = db.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_id == document_data["id"]
            )
        )
        assert document is not None
        assert task is not None
        assert version is not None and version.status == "ready"
        assert chunk_total and chunk_total >= 1
        stored_path = Path(document.file_path)
        assert stored_path.is_file()
        assert stored_path.read_bytes() == content


def test_document_upload_validation_rejects_bad_empty_and_large_files(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers)
    unsupported = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("notes.docx", b"not a document", "application/octet-stream")},
    )
    assert unsupported.status_code == 415
    assert unsupported.json()["detail"] == "FILE_TYPE_UNSUPPORTED"

    empty = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert empty.status_code == 422
    assert empty.json()["detail"] == "FILE_EMPTY"

    client.app.state.settings.max_upload_bytes = 16
    too_large = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("large.txt", b"x" * 17, "text/plain")},
    )
    assert too_large.status_code == 413
    assert too_large.json()["detail"] == "FILE_TOO_LARGE"
    listed = client.get(f"/api/v1/courses/{course_id}/documents", headers=auth_headers)
    assert listed.json()["data"] == {"items": [], "total": 0}


def test_document_and_task_are_isolated_between_users(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers)
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("private.txt", b"Private course material", "text/plain")},
    ).json()["data"]
    document_id = uploaded["document"]["id"]
    task_id = uploaded["async_task_id"]

    assert client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("anonymous.txt", b"anonymous", "text/plain")},
    ).status_code == 401

    second_headers = _second_user(client)
    assert client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=second_headers,
        files={"file": ("intrusion.txt", b"intrusion", "text/plain")},
    ).status_code == 404
    assert client.get(
        f"/api/v1/courses/{course_id}/documents", headers=second_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/documents/{document_id}", headers=second_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/async-tasks/{task_id}", headers=second_headers
    ).status_code == 404


def test_failed_document_parse_records_consistent_error_state(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers)
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("whitespace.txt", b"   \n\t", "text/plain")},
    )
    assert uploaded.status_code == 201
    data = uploaded.json()["data"]
    assert data["document"]["status"] == "failed"
    assert data["document"]["error_message"] == "DOCUMENT_TEXT_EMPTY"

    task = client.get(
        f"/api/v1/async-tasks/{data['async_task_id']}", headers=auth_headers
    ).json()["data"]
    assert task["status"] == "failed"
    assert task["error_message"] == "DOCUMENT_TEXT_EMPTY"

    with client.app.state.database.session_factory() as db:
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == data["document"]["id"]
            )
        )
        assert version is not None
        assert version.status == "failed"
        assert version.error_message == "DOCUMENT_TEXT_EMPTY"
