from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import AsyncTask, Course, Document, DocumentChunk, DocumentVersion


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


def test_reparse_allocates_after_failed_version_without_reusing_its_number(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Document reparse retry")
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={"file": ("retry.txt", b"Valid material for a retry.", "text/plain")},
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["data"]["document"]["id"]

    with client.app.state.database.session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None and document.current_version == 1
        db.add(
            DocumentVersion(
                document_id=document_id,
                version_no=2,
                file_path=document.file_path,
                status="failed",
                error_message="simulated provider failure",
            )
        )
        db.commit()

    reparsed = client.post(
        f"/api/v1/documents/{document_id}/reparse", headers=auth_headers
    )
    assert reparsed.status_code == 200
    assert reparsed.json()["data"]["version"] == 3

    versions = client.get(
        f"/api/v1/documents/{document_id}/versions", headers=auth_headers
    )
    assert versions.status_code == 200
    items = versions.json()["data"]["items"]
    assert [item["version"] for item in items] == [3, 2, 1]
    assert items[0]["status"] == "ready"
    assert items[0]["is_current"] is True
    assert items[1]["status"] == "failed"


def test_document_task_detail_requires_the_matching_document_resource_chain(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Document task course A")
    course_b = _course(client, auth_headers, "Document task course B")

    def upload(course_id: int, filename: str) -> dict:
        response = client.post(
            f"/api/v1/courses/{course_id}/documents",
            headers=auth_headers,
            files={"file": (filename, f"content for {filename}".encode(), "text/plain")},
        )
        assert response.status_code == 201
        return response.json()["data"]

    uploaded_a = upload(course_a, "a.txt")
    uploaded_a_second = upload(course_a, "a-second.txt")
    uploaded_b = upload(course_b, "b.txt")
    document_a = uploaded_a["document"]["id"]
    document_a_second = uploaded_a_second["document"]["id"]
    document_b = uploaded_b["document"]["id"]
    task_a = uploaded_a["async_task_id"]
    task_a_second = uploaded_a_second["async_task_id"]
    task_b = uploaded_b["async_task_id"]

    # The valid, document-scoped response retains the general task endpoint's shape.
    scoped = client.get(
        f"/api/v1/documents/{document_a}/tasks/{task_a}", headers=auth_headers
    )
    general = client.get(f"/api/v1/async-tasks/{task_a}", headers=auth_headers)
    assert scoped.status_code == 200
    assert general.status_code == 200
    expected_fields = {
        "task_id", "task_type", "status", "progress", "current_step", "result_data",
        "error_message", "retry_count", "cancel_requested", "created_at",
    }
    assert expected_fields <= scoped.json()["data"].keys()
    assert {
        key: scoped.json()["data"][key] for key in expected_fields
    } == {
        key: general.json()["data"][key] for key in expected_fields
    }

    # The existing latest-task endpoint remains available for a valid document.
    latest = client.get(
        f"/api/v1/documents/{document_a}/tasks/latest", headers=auth_headers
    )
    assert latest.status_code == 200
    assert latest.json()["data"]["task_id"] == task_a

    # A task from another document is not readable, even under the same course/user.
    same_course_mismatch = client.get(
        f"/api/v1/documents/{document_a}/tasks/{task_a_second}", headers=auth_headers
    )
    assert same_course_mismatch.status_code == 404
    assert same_course_mismatch.json()["detail"] == "TASK_NOT_FOUND"

    # A task from a document in another course is likewise hidden.
    cross_course_mismatch = client.get(
        f"/api/v1/documents/{document_a}/tasks/{task_b}", headers=auth_headers
    )
    assert cross_course_mismatch.status_code == 404
    assert cross_course_mismatch.json()["detail"] == "TASK_NOT_FOUND"

    # A document-shaped but non-processing task cannot be exposed by this endpoint.
    with client.app.state.database.session_factory() as db:
        owner_task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_a))
        assert owner_task is not None
        non_document_task = AsyncTask(
            user_id=owner_task.user_id,
            public_id="non-document-task",
            task_type="weekly_report",
            resource_type="document",
            resource_id=str(document_a),
        )
        db.add(non_document_task)
        db.commit()
    assert client.get(
        f"/api/v1/documents/{document_a}/tasks/non-document-task", headers=auth_headers
    ).status_code == 404

    # Other users cannot use either document or task identifiers to discover the task.
    second_headers = _second_user(client)
    other_user = client.get(
        f"/api/v1/documents/{document_a}/tasks/{task_a}", headers=second_headers
    )
    assert other_user.status_code == 404
    assert other_user.json()["detail"] == "TASK_NOT_FOUND"

    # Archived courses and soft-deleted documents invalidate their document-task chain.
    with client.app.state.database.session_factory() as db:
        course = db.get(Course, course_b)
        document = db.get(Document, document_a_second)
        assert course is not None and document is not None
        course.archived = True
        document.is_deleted = True
        document.status = "deleted"
        db.commit()
    assert client.get(
        f"/api/v1/documents/{document_b}/tasks/{task_b}", headers=auth_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/documents/{document_a_second}/tasks/{task_a_second}", headers=auth_headers
    ).status_code == 404
