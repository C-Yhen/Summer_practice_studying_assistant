from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.database import Database
from backend.app.models import (
    Course,
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    PracticeAttempt,
    PracticeQuestion,
    WrongQuestionEntry,
)


def _course(client: TestClient, headers: dict, name: str = "Machine Learning") -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _other_user(client: TestClient) -> dict:
    credentials = {
        "email": "practice-other@example.com",
        "password": "practice-password",
        "display_name": "Other",
    }
    assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": credentials["email"], "password": credentials["password"]},
    )
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _point(client: TestClient, course_id: int, name: str = "Gradient descent") -> int:
    with client.app.state.database.session_factory() as db:
        point = KnowledgePoint(
            course_id=course_id,
            name=name,
            description=f"Description for {name}",
            difficulty="intermediate",
        )
        db.add(point)
        db.commit()
        db.refresh(point)
        return point.id


def _raw_question(
    client: TestClient,
    course_id: int,
    *,
    point_id: int | None,
    seed: str,
    stem: str,
) -> int:
    with client.app.state.database.session_factory() as db:
        question = PracticeQuestion(
            course_id=course_id,
            knowledge_point_id=point_id,
            seed_key=seed,
            stem=stem,
            options=[
                {"key": "A", "text": "Correct"},
                {"key": "B", "text": "Incorrect"},
            ],
            correct_option="A",
            explanation="Because A is correct.",
        )
        db.add(question)
        db.commit()
        db.refresh(question)
        return question.id


def _bootstrap_question(
    client: TestClient,
    headers: dict,
    course_id: int,
    point_name: str = "Gradient descent",
) -> dict:
    _point(client, course_id, point_name)
    response = client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=headers,
    )
    assert response.status_code == 200
    response = client.get(
        f"/api/v1/courses/{course_id}/practice/questions",
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["data"]["items"][0]


def _submit(
    client: TestClient,
    headers: dict,
    course_id: int,
    question_id: int,
    *,
    submission_id: str,
    selected_option: str = "B",
    elapsed_seconds: int = 12,
):
    return client.post(
        f"/api/v1/courses/{course_id}/practice/questions/{question_id}/attempts",
        headers=headers,
        json={
            "submission_id": submission_id,
            "selected_option": selected_option,
            "elapsed_seconds": elapsed_seconds,
        },
    )


def _counts(client: TestClient) -> tuple[int, int, int]:
    with client.app.state.database.session_factory() as db:
        return (
            db.scalar(select(func.count()).select_from(PracticeAttempt)) or 0,
            db.scalar(
                select(func.count())
                .select_from(LearningRecord)
                .where(LearningRecord.record_type == "practice")
            )
            or 0,
            db.scalar(select(func.count()).select_from(WrongQuestionEntry)) or 0,
        )


def test_bootstrap_creates_course_questions_and_is_idempotent(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    _point(client, course_id, "Point A")
    _point(client, course_id, "Point B")

    first = client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=auth_headers,
    ).json()["data"]
    second = client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=auth_headers,
    ).json()["data"]

    assert first == {
        "created_count": 2,
        "existing_count": 0,
        "total": 2,
        "reason": None,
    }
    assert second == {
        "created_count": 0,
        "existing_count": 2,
        "total": 2,
        "reason": None,
    }
    with client.app.state.database.session_factory() as db:
        questions = list(
            db.scalars(
                select(PracticeQuestion).where(PracticeQuestion.course_id == course_id)
            )
        )
        assert len(questions) == 2


def test_bootstrap_without_points_does_not_create_fake_questions(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    result = client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=auth_headers,
    )
    assert result.status_code == 200
    assert result.json()["data"] == {
        "created_count": 0,
        "existing_count": 0,
        "total": 0,
        "reason": "NO_KNOWLEDGE_POINTS",
    }
    assert client.get(
        f"/api/v1/courses/{course_id}/practice/questions", headers=auth_headers
    ).json()["data"]["total"] == 0


def test_bootstrap_rejects_other_user_and_archived_course(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    other_headers = _other_user(client)
    assert client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=other_headers,
    ).status_code == 404
    with client.app.state.database.session_factory() as db:
        course = db.get(Course, course_id)
        course.archived = True
        db.commit()
    assert client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=auth_headers,
    ).status_code == 404


def test_question_list_hides_answers_has_real_total_and_is_read_only(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    for name in ("Point A", "Point B", "Point C"):
        _point(client, course_id, name)
    client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=auth_headers,
    )

    before = _counts(client)
    response = client.get(
        f"/api/v1/courses/{course_id}/practice/questions?limit=1",
        headers=auth_headers,
    )
    data = response.json()["data"]
    assert response.status_code == 200
    assert len(data["items"]) == 1
    assert data["total"] == 3
    assert "correct_option" not in data["items"][0]
    assert "explanation" not in data["items"][0]
    assert _counts(client) == before


def test_question_list_validates_knowledge_point_course(
    client: TestClient, auth_headers: dict
):
    course_a = _course(client, auth_headers, "Course A")
    course_b = _course(client, auth_headers, "Course B")
    point_a = _point(client, course_a, "A point")
    point_b = _point(client, course_b, "B point")
    client.post(
        f"/api/v1/courses/{course_a}/practice/questions/bootstrap",
        headers=auth_headers,
    )

    valid = client.get(
        f"/api/v1/courses/{course_a}/practice/questions?knowledge_point_id={point_a}",
        headers=auth_headers,
    )
    invalid = client.get(
        f"/api/v1/courses/{course_a}/practice/questions?knowledge_point_id={point_b}",
        headers=auth_headers,
    )
    assert valid.status_code == 200
    assert valid.json()["data"]["total"] == 1
    assert invalid.status_code == 404
    assert invalid.json()["detail"] == "KNOWLEDGE_POINT_NOT_FOUND"


@pytest.mark.parametrize(
    ("selected_option", "expect_correct"),
    [("A", True), ("B", False)],
)
def test_attempt_scores_and_updates_mastery_direction(
    client: TestClient,
    auth_headers: dict,
    selected_option: str,
    expect_correct: bool,
):
    course_id = _course(client, auth_headers)
    question = _bootstrap_question(client, auth_headers, course_id)
    response = _submit(
        client,
        auth_headers,
        course_id,
        question["id"],
        submission_id=f"direction-{selected_option}-001",
        selected_option=selected_option,
    )
    data = response.json()["data"]
    assert response.status_code == 200
    assert data["is_correct"] is expect_correct
    assert data["correct_option"] == "A"
    assert data["idempotent_replay"] is False
    assert data["mastery_score"] >= 0.3 if expect_correct else data["mastery_score"] <= 0.3
    with client.app.state.database.session_factory() as db:
        mastery = db.scalar(select(KnowledgeMastery))
        assert mastery.attempts == 1
        assert mastery.correct_attempts == int(expect_correct)
        record = db.scalar(select(LearningRecord))
        assert record.duration_seconds == 12
        assert record.record_type == "practice"


def test_attempt_without_knowledge_point_still_creates_learning_record(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    question_id = _raw_question(
        client,
        course_id,
        point_id=None,
        seed="manual-without-point",
        stem="Question without point",
    )
    response = _submit(
        client,
        auth_headers,
        course_id,
        question_id,
        submission_id="without-point-001",
    )
    assert response.status_code == 200
    assert response.json()["data"]["mastery_score"] is None
    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(KnowledgeMastery)) == 0
        record = db.scalar(select(LearningRecord))
        assert record.knowledge_point_id is None
        assert record.course_id == course_id


def test_identical_submission_replays_full_contract_without_side_effects(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    question = _bootstrap_question(client, auth_headers, course_id)
    request = dict(
        submission_id="stable-replay-001",
        selected_option="B",
        elapsed_seconds=17,
    )
    first = _submit(client, auth_headers, course_id, question["id"], **request)
    replay = _submit(client, auth_headers, course_id, question["id"], **request)
    first_data = first.json()["data"]
    replay_data = replay.json()["data"]

    assert replay.status_code == 200
    assert replay_data["attempt_id"] == first_data["attempt_id"]
    assert replay_data["idempotent_replay"] is True
    for field in (
        "question_id",
        "selected_option",
        "is_correct",
        "correct_option",
        "explanation",
        "origin",
        "source_document_id",
        "source_page_number",
        "source_quote",
        "mastery_score",
        "wrong_book_updated",
        "summary",
    ):
        assert replay_data[field] == first_data[field]
    assert _counts(client) == (1, 1, 1)
    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(KnowledgeMastery.attempts)) == 1
        assert db.scalar(select(WrongQuestionEntry.wrong_count)) == 1


@pytest.mark.parametrize("changed_field", ["question", "course", "option", "elapsed"])
def test_reused_submission_with_different_request_returns_409_without_leak(
    client: TestClient, auth_headers: dict, changed_field: str
):
    course_a = _course(client, auth_headers, "Course A")
    course_b = _course(client, auth_headers, "Course B")
    question_a = _bootstrap_question(client, auth_headers, course_a, "A point")
    question_b = _bootstrap_question(client, auth_headers, course_b, "B point")
    key = "reused-request-001"
    assert _submit(
        client,
        auth_headers,
        course_a,
        question_a["id"],
        submission_id=key,
        selected_option="B",
        elapsed_seconds=12,
    ).status_code == 200

    target_course = course_b if changed_field == "course" else course_a
    target_question = question_b["id"] if changed_field in {"question", "course"} else question_a["id"]
    selected_option = "A" if changed_field == "option" else "B"
    elapsed = 99 if changed_field == "elapsed" else 12
    response = _submit(
        client,
        auth_headers,
        target_course,
        target_question,
        submission_id=key,
        selected_option=selected_option,
        elapsed_seconds=elapsed,
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "IDEMPOTENCY_KEY_REUSED"}
    assert "stem" not in response.text
    assert _counts(client) == (1, 1, 1)


def test_attempt_rejects_invalid_option_cross_course_and_cross_user(
    client: TestClient, auth_headers: dict
):
    course_a = _course(client, auth_headers, "Course A")
    course_b = _course(client, auth_headers, "Course B")
    question = _bootstrap_question(client, auth_headers, course_a)
    other_headers = _other_user(client)
    assert _submit(
        client,
        auth_headers,
        course_a,
        question["id"],
        submission_id="invalid-option-001",
        selected_option="Z",
    ).status_code == 422
    assert _submit(
        client,
        auth_headers,
        course_b,
        question["id"],
        submission_id="cross-course-001",
    ).status_code == 404
    assert _submit(
        client,
        other_headers,
        course_a,
        question["id"],
        submission_id="cross-user-001",
    ).status_code == 404
    assert _counts(client) == (0, 0, 0)


def test_repeated_wrong_answer_reuses_entry_and_restores_pending(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    question = _bootstrap_question(client, auth_headers, course_id)
    assert _submit(
        client,
        auth_headers,
        course_id,
        question["id"],
        submission_id="wrong-first-001",
    ).status_code == 200
    book = client.get(
        f"/api/v1/courses/{course_id}/wrong-book", headers=auth_headers
    ).json()["data"]
    entry_id = book["items"][0]["id"]
    for _ in range(2):
        response = client.patch(
            f"/api/v1/courses/{course_id}/wrong-book/{entry_id}",
            headers=auth_headers,
            json={"status": "mastered"},
        )
        assert response.status_code == 200

    assert _submit(
        client,
        auth_headers,
        course_id,
        question["id"],
        submission_id="wrong-second-001",
    ).status_code == 200
    with client.app.state.database.session_factory() as db:
        entries = list(db.scalars(select(WrongQuestionEntry)))
        assert len(entries) == 1
        assert entries[0].wrong_count == 2
        assert entries[0].status == "pending"
        assert entries[0].mastered_at is None


def test_removed_entry_is_idempotent_hidden_and_excluded_from_wrong_mode(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    question = _bootstrap_question(client, auth_headers, course_id)
    _submit(
        client,
        auth_headers,
        course_id,
        question["id"],
        submission_id="remove-wrong-001",
    )
    book = client.get(
        f"/api/v1/courses/{course_id}/wrong-book", headers=auth_headers
    ).json()["data"]
    entry_id = book["items"][0]["id"]
    for _ in range(2):
        response = client.patch(
            f"/api/v1/courses/{course_id}/wrong-book/{entry_id}",
            headers=auth_headers,
            json={"status": "removed"},
        )
        assert response.status_code == 200

    book = client.get(
        f"/api/v1/courses/{course_id}/wrong-book", headers=auth_headers
    ).json()["data"]
    wrong_mode = client.get(
        f"/api/v1/courses/{course_id}/practice/questions?mode=wrong",
        headers=auth_headers,
    ).json()["data"]
    assert book["items"] == []
    assert book["total"] == 0
    assert book["summary"] == {"pending": 0, "mastered": 0, "repeated_wrong": 0}
    assert wrong_mode["items"] == []
    assert wrong_mode["total"] == 0


def test_wrong_book_total_search_pagination_and_global_summary(
    client: TestClient, auth_headers: dict
):
    course_id = _course(client, auth_headers)
    alpha = _bootstrap_question(client, auth_headers, course_id, "Alpha point")
    beta_point = _point(client, course_id, "Beta point")
    beta_id = _raw_question(
        client,
        course_id,
        point_id=beta_point,
        seed="manual-beta",
        stem="Beta searchable question",
    )
    _submit(
        client,
        auth_headers,
        course_id,
        alpha["id"],
        submission_id="alpha-wrong-001",
    )
    _submit(
        client,
        auth_headers,
        course_id,
        alpha["id"],
        submission_id="alpha-wrong-002",
    )
    _submit(
        client,
        auth_headers,
        course_id,
        beta_id,
        submission_id="beta-wrong-001",
    )
    all_book = client.get(
        f"/api/v1/courses/{course_id}/wrong-book?limit=1",
        headers=auth_headers,
    ).json()["data"]
    beta_entry = next(
        item
        for item in client.get(
            f"/api/v1/courses/{course_id}/wrong-book?limit=10",
            headers=auth_headers,
        ).json()["data"]["items"]
        if item["question"]["id"] == beta_id
    )
    client.patch(
        f"/api/v1/courses/{course_id}/wrong-book/{beta_entry['id']}",
        headers=auth_headers,
        json={"status": "mastered"},
    )

    pending = client.get(
        f"/api/v1/courses/{course_id}/wrong-book?status=pending&limit=1&offset=0",
        headers=auth_headers,
    ).json()["data"]
    searched = client.get(
        f"/api/v1/courses/{course_id}/wrong-book?q=Beta&limit=1",
        headers=auth_headers,
    ).json()["data"]
    expected_summary = {"pending": 1, "mastered": 1, "repeated_wrong": 1}
    assert len(all_book["items"]) == 1
    assert all_book["total"] == 2
    assert pending["total"] == 1
    assert searched["total"] == 1
    assert pending["summary"] == expected_summary
    assert searched["summary"] == expected_summary


def test_wrong_book_and_wrong_mode_enforce_user_and_course_isolation(
    client: TestClient, auth_headers: dict
):
    course_a = _course(client, auth_headers, "Course A")
    course_b = _course(client, auth_headers, "Course B")
    question = _bootstrap_question(client, auth_headers, course_a)
    _submit(
        client,
        auth_headers,
        course_a,
        question["id"],
        submission_id="isolated-wrong-001",
    )
    book = client.get(
        f"/api/v1/courses/{course_a}/wrong-book", headers=auth_headers
    ).json()["data"]
    entry_id = book["items"][0]["id"]
    other_headers = _other_user(client)

    assert client.get(
        f"/api/v1/courses/{course_a}/wrong-book", headers=other_headers
    ).status_code == 404
    assert client.patch(
        f"/api/v1/courses/{course_a}/wrong-book/{entry_id}",
        headers=other_headers,
        json={"status": "mastered"},
    ).status_code == 404
    assert client.patch(
        f"/api/v1/courses/{course_b}/wrong-book/{entry_id}",
        headers=auth_headers,
        json={"status": "mastered"},
    ).status_code == 404
    assert client.get(
        f"/api/v1/courses/{course_b}/practice/questions?mode=wrong",
        headers=auth_headers,
    ).json()["data"]["total"] == 0


@pytest.mark.skipif(
    not os.getenv("ROUND11_API_BASE_URL")
    or not (
        os.getenv("ROUND11_POSTGRES_URL")
        or os.getenv("DATABASE_URL", "")
    ).startswith("postgresql"),
    reason="requires the opt-in PostgreSQL API environment",
)
def test_postgres_concurrent_submission_and_api_contract():
    base_url = os.environ["ROUND11_API_BASE_URL"].rstrip("/")
    database = Database(
        os.getenv("ROUND11_POSTGRES_URL") or os.environ["DATABASE_URL"]
    )
    unique = uuid.uuid4().hex
    credentials = {
        "email": f"round11-{unique}@example.com",
        "password": "round11-postgres-password",
        "display_name": "Round 11 PostgreSQL",
    }
    with httpx.Client(timeout=15) as api:
        assert api.post(f"{base_url}/auth/register", json=credentials).status_code == 201
        login = api.post(
            f"{base_url}/auth/login",
            json={"email": credentials["email"], "password": credentials["password"]},
        )
        assert login.status_code == 200
        login_data = login.json()["data"]
        headers = {"Authorization": f"Bearer {login_data['access_token']}"}
        course_a = api.post(
            f"{base_url}/courses", headers=headers, json={"name": "Concurrent A"}
        ).json()["data"]["id"]
        course_b = api.post(
            f"{base_url}/courses", headers=headers, json={"name": "Concurrent B"}
        ).json()["data"]["id"]

        with database.session_factory() as db:
            point_a1 = KnowledgePoint(course_id=course_a, name=f"Alpha {unique}")
            point_a2 = KnowledgePoint(course_id=course_a, name=f"Beta {unique}")
            point_b = KnowledgePoint(course_id=course_b, name=f"Other {unique}")
            db.add_all([point_a1, point_a2, point_b])
            db.commit()

        assert api.post(
            f"{base_url}/courses/{course_a}/practice/questions/bootstrap",
            headers=headers,
        ).status_code == 200
        assert api.post(
            f"{base_url}/courses/{course_b}/practice/questions/bootstrap",
            headers=headers,
        ).status_code == 200
        questions_a = api.get(
            f"{base_url}/courses/{course_a}/practice/questions", headers=headers
        ).json()["data"]["items"]
        question_b = api.get(
            f"{base_url}/courses/{course_b}/practice/questions", headers=headers
        ).json()["data"]["items"][0]
        question_a1, question_a2 = questions_a
        submission_id = f"concurrent-{unique}"
        payload = {
            "submission_id": submission_id,
            "selected_option": "B",
            "elapsed_seconds": 23,
        }
        start_barrier = Barrier(2)

        def send_same_submission():
            start_barrier.wait()
            with httpx.Client(timeout=15) as concurrent_api:
                return concurrent_api.post(
                    f"{base_url}/courses/{course_a}/practice/questions/{question_a1['id']}/attempts",
                    headers=headers,
                    json=payload,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: send_same_submission(), range(2)))
        assert [response.status_code for response in responses] == [200, 200]
        response_data = [response.json()["data"] for response in responses]
        assert len({item["attempt_id"] for item in response_data}) == 1
        assert sorted(item["idempotent_replay"] for item in response_data) == [False, True]

        with database.session_factory() as db:
            user_id = login_data["user"]["id"]
            attempt_count = db.scalar(
                select(func.count())
                .select_from(PracticeAttempt)
                .where(
                    PracticeAttempt.user_id == user_id,
                    PracticeAttempt.submission_id == submission_id,
                )
            )
            learning_count = db.scalar(
                select(func.count())
                .select_from(LearningRecord)
                .where(
                    LearningRecord.user_id == user_id,
                    LearningRecord.course_id == course_a,
                    LearningRecord.record_type == "practice",
                )
            )
            mastery = db.scalar(
                select(KnowledgeMastery).where(
                    KnowledgeMastery.user_id == user_id,
                    KnowledgeMastery.knowledge_point_id
                    == question_a1["knowledge_point_id"],
                )
            )
            wrong = db.scalar(
                select(WrongQuestionEntry).where(
                    WrongQuestionEntry.user_id == user_id,
                    WrongQuestionEntry.question_id == question_a1["id"],
                )
            )
            assert attempt_count == 1
            assert learning_count == 1
            assert mastery.attempts == 1
            assert wrong.wrong_count == 1

        for target_course, target_question, option in (
            (course_a, question_a2["id"], "B"),
            (course_b, question_b["id"], "B"),
            (course_a, question_a1["id"], "A"),
        ):
            conflict = api.post(
                f"{base_url}/courses/{target_course}/practice/questions/{target_question}/attempts",
                headers=headers,
                json={**payload, "selected_option": option},
            )
            assert conflict.status_code == 409
            assert conflict.json() == {"detail": "IDEMPOTENCY_KEY_REUSED"}
            assert "stem" not in conflict.text

        for suffix, question_id in (
            ("repeat", question_a1["id"]),
            ("second-question", question_a2["id"]),
        ):
            assert api.post(
                f"{base_url}/courses/{course_a}/practice/questions/{question_id}/attempts",
                headers=headers,
                json={
                    "submission_id": f"{suffix}-{unique}",
                    "selected_option": "B",
                    "elapsed_seconds": 11,
                },
            ).status_code == 200

        limited = api.get(
            f"{base_url}/courses/{course_a}/wrong-book?limit=1",
            headers=headers,
        ).json()["data"]
        searched = api.get(
            f"{base_url}/courses/{course_a}/wrong-book?q=Alpha&limit=1",
            headers=headers,
        ).json()["data"]
        pending_page = api.get(
            f"{base_url}/courses/{course_a}/wrong-book?status=pending&limit=1&offset=1",
            headers=headers,
        ).json()["data"]
        assert len(limited["items"]) == 1
        assert limited["total"] == 2
        assert searched["total"] == 1
        assert pending_page["total"] == 2
        assert len(pending_page["items"]) == 1
        assert limited["summary"] == searched["summary"] == pending_page["summary"]
        assert limited["summary"] == {
            "pending": 2,
            "mastered": 0,
            "repeated_wrong": 1,
        }
