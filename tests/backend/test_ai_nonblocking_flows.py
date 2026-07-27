from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.models import AsyncTask, Course, KnowledgePoint, PracticeAttempt, PracticeQuestion
from backend.app.providers.llm import LLMProvider
from backend.app.services.ai_enrichment import process_ai_enhancement
from backend.app.services.practice_gen import AIQuestionPayload, persist_ai_questions


def _course(client: TestClient, headers: dict[str, str], name: str = "AI nonblocking") -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _point(client: TestClient, course_id: int, name: str = "Point") -> int:
    with client.app.state.database.session_factory() as db:
        point = KnowledgePoint(course_id=course_id, name=name, difficulty="basic", estimated_minutes=30)
        db.add(point)
        db.commit()
        return point.id


def _enable_remote_task_queue(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    client.app.state.settings.llm_provider = "fake-remote"
    queued: list[str] = []

    async def no_network_dispatch(db, task, settings) -> None:
        queued.append(task.task_type)

    monkeypatch.setattr("backend.app.services.ai_enrichment.dispatch_async_task", no_network_dispatch)
    return queued


def test_rule_endpoints_return_without_waiting_for_slow_remote_ai(client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """A remote provider may take >8s; API routes only enqueue it and return."""
    course_id = _course(client, auth_headers)
    _point(client, course_id)
    queued = _enable_remote_task_queue(client, monkeypatch)

    started = time.perf_counter()
    recommendations = client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers)
    elapsed_recommendations = time.perf_counter() - started
    assert recommendations.status_code == 200
    assert elapsed_recommendations < 1
    assert recommendations.json()["data"]["items"]
    assert recommendations.json()["data"]["ai_enhancement"]["status"] == "queued"

    started = time.perf_counter()
    plan = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=auth_headers,
        json={"goal": "finish core review", "start_date": "2026-08-01", "end_date": "2026-08-03"},
    )
    elapsed_plan = time.perf_counter() - started
    assert plan.status_code == 200
    assert elapsed_plan < 2
    generated = plan.json()["data"]
    assert generated["candidate_version"]["tasks"]
    assert generated["ai_enhancement_task_id"]

    started = time.perf_counter()
    practice = client.post(f"/api/v1/courses/{course_id}/practice/questions/bootstrap", headers=auth_headers)
    elapsed_practice = time.perf_counter() - started
    assert practice.status_code == 200
    assert elapsed_practice < 2
    body = practice.json()["data"]
    assert body["generation_mode"] == "rule_first"
    assert body["rule_created_count"] >= 1
    assert body["ai_enhancement_task_id"]
    listed = client.get(f"/api/v1/courses/{course_id}/practice/questions", headers=auth_headers).json()["data"]
    assert listed["items"] and all(len(item["options"]) == 4 for item in listed["items"])
    assert {"ai_recommendation", "plan_ai_enhancement", "practice_ai_enhancement"}.issubset(queued)


def test_eight_second_fake_llm_runs_only_in_background_task(client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowProvider(LLMProvider):
        async def chat(self, messages, **kwargs):
            await asyncio.sleep(8.1)
            return '{"summary":"background only","recommendations":[]}'

        async def embed(self, texts):
            return [[0.0] * 1024 for _ in texts]

    course_id = _course(client, auth_headers, "Eight second AI")
    _point(client, course_id)
    _enable_remote_task_queue(client, monkeypatch)
    started = time.perf_counter()
    response = client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers)
    endpoint_elapsed = time.perf_counter() - started
    assert response.status_code == 200 and endpoint_elapsed < 1
    task_id = response.json()["data"]["ai_enhancement"]["task_id"]
    monkeypatch.setattr("backend.app.services.ai_enrichment.get_llm_provider", lambda settings: SlowProvider())
    with client.app.state.database.session_factory() as db:
        task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id))
        assert task is not None
        started = time.perf_counter()
        result = asyncio.run(process_ai_enhancement(db, task, client.app.state.settings))
        assert time.perf_counter() - started >= 8
        assert result["summary"] == "background only"


def test_slow_plan_and_practice_enhancements_do_not_delay_rule_routes(client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan and practice use the same worker boundary as recommendations."""
    course_id = _course(client, auth_headers, "Slow plan and practice AI")
    _point(client, course_id)
    _enable_remote_task_queue(client, monkeypatch)

    started = time.perf_counter()
    plan_response = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=auth_headers,
        json={"goal": "rule candidate first", "start_date": "2026-08-01", "end_date": "2026-08-03"},
    )
    assert plan_response.status_code == 200 and time.perf_counter() - started < 2
    started = time.perf_counter()
    practice_response = client.post(f"/api/v1/courses/{course_id}/practice/questions/bootstrap", headers=auth_headers)
    assert practice_response.status_code == 200 and time.perf_counter() - started < 2

    async def slow_plan(*args, **kwargs):
        await asyncio.sleep(8.1)
        return {"summary": "background plan", "risks": [], "tasks": []}

    async def slow_practice(*args, **kwargs):
        await asyncio.sleep(8.1)
        return []

    monkeypatch.setattr("backend.app.services.ai_enrichment.get_llm_provider", lambda settings: object())
    monkeypatch.setattr("backend.app.services.ai_enrichment.generate_plan_one_shot", slow_plan)
    monkeypatch.setattr("backend.app.services.ai_enrichment.generate_questions_batch", slow_practice)
    with client.app.state.database.session_factory() as db:
        plan_task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == plan_response.json()["data"]["ai_enhancement_task_id"]))
        practice_task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == practice_response.json()["data"]["ai_enhancement_task_id"]))
        assert plan_task is not None and practice_task is not None
        started = time.perf_counter()
        assert asyncio.run(process_ai_enhancement(db, plan_task, client.app.state.settings))["summary"] == "background plan"
        assert time.perf_counter() - started >= 8
        started = time.perf_counter()
        assert asyncio.run(process_ai_enhancement(db, practice_task, client.app.state.settings))["ai_created_count"] == 0
        assert time.perf_counter() - started >= 8


def test_rule_plan_remains_confirmable_when_ai_is_only_queued(client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    course_id = _course(client, auth_headers, "Confirmable rule plan")
    _point(client, course_id)
    _enable_remote_task_queue(client, monkeypatch)
    generated = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=auth_headers,
        json={"goal": "confirm candidate", "start_date": "2026-08-01", "end_date": "2026-08-03"},
    ).json()["data"]
    confirmed = client.post(
        f"/api/v1/study-plans/{generated['plan_id']}/versions/1/confirm",
        headers=auth_headers,
        json={"expected_base_version": 0, "confirmation_token": generated["confirmation_token"]},
    )
    assert confirmed.status_code == 200


def test_identical_plan_input_reuses_ai_enhancement_task(client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    course_id = _course(client, auth_headers, "Deduplicated plan enhancement")
    _point(client, course_id)
    queued = _enable_remote_task_queue(client, monkeypatch)
    payload = {"goal": "same input", "start_date": "2026-08-01", "end_date": "2026-08-03"}
    first = client.post(f"/api/v1/courses/{course_id}/study-plans/generate", headers=auth_headers, json=payload)
    second = client.post(f"/api/v1/courses/{course_id}/study-plans/generate", headers=auth_headers, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["ai_enhancement_task_id"] == second.json()["data"]["ai_enhancement_task_id"]
    assert queued.count("plan_ai_enhancement") == 1


@pytest.mark.parametrize("payload", [
    {"knowledge_point_id": 1, "stem": "x", "options": [{"label": "A", "text": "x"}, {"label": "B", "text": "x"}], "correct_option": "A", "explanation": "x", "source_quote": "x", "difficulty": "basic"},
    {"knowledge_point_id": 1, "stem": "x", "options": [{"label": "A", "text": "x"}, {"label": "A", "text": "x"}, {"label": "C", "text": "x"}, {"label": "D", "text": "x"}], "correct_option": "A", "explanation": "x", "source_quote": "x", "difficulty": "basic"},
    {"knowledge_point_id": 1, "stem": "x", "options": [{"label": "A", "text": "x"}, {"label": "B", "text": "x"}, {"label": "C", "text": "x"}, {"label": "D", "text": "x"}], "correct_option": "Z", "explanation": "x", "source_quote": "x", "difficulty": "basic"},
])
def test_invalid_ai_question_shapes_are_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        AIQuestionPayload.model_validate(payload)


def test_inactive_question_does_not_block_new_rule_question(client: TestClient, auth_headers: dict[str, str]) -> None:
    course_id = _course(client, auth_headers, "Inactive question")
    point_id = _point(client, course_id)
    with client.app.state.database.session_factory() as db:
        db.add(PracticeQuestion(course_id=course_id, knowledge_point_id=point_id, seed_key=f"rule_seed:kp:{point_id}", stem="old", options=[{"key": "A", "text": "old"}], correct_option="A", explanation="old", is_active=False))
        db.commit()
    result = client.post(f"/api/v1/courses/{course_id}/practice/questions/bootstrap", headers=auth_headers)
    assert result.status_code == 200 and result.json()["data"]["rule_created_count"] == 1
    with client.app.state.database.session_factory() as db:
        active = list(db.scalars(select(PracticeQuestion).where(PracticeQuestion.course_id == course_id, PracticeQuestion.is_active.is_(True))))
        assert len(active) == 1 and active[0].seed_key != f"rule_seed:kp:{point_id}"


def test_valid_ai_enhancement_preserves_existing_attempt_history(client: TestClient, auth_headers: dict[str, str]) -> None:
    course_id = _course(client, auth_headers, "Preserve history")
    point_id = _point(client, course_id)
    client.post(f"/api/v1/courses/{course_id}/practice/questions/bootstrap", headers=auth_headers)
    with client.app.state.database.session_factory() as db:
        owner_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        rule = db.scalar(select(PracticeQuestion).where(PracticeQuestion.course_id == course_id, PracticeQuestion.is_active.is_(True)))
        assert rule is not None
        db.add(PracticeAttempt(submission_id="history-kept-123", user_id=owner_id, course_id=course_id, question_id=rule.id, selected_option="A", is_correct=True))
        db.commit()
        result = persist_ai_questions(db, course_id=course_id, questions=[{
            "knowledge_point_id": point_id, "stem": "A valid enriched question?",
            "options": [{"label": "A", "text": "one"}, {"label": "B", "text": "two"}, {"label": "C", "text": "three"}, {"label": "D", "text": "four"}],
            "correct_option": "A", "explanation": "because one", "source_quote": "course material quote", "difficulty": "basic",
        }])
        db.commit()
        assert result["ai_created_count"] == 1
        assert db.get(PracticeQuestion, rule.id) is not None
        assert db.scalar(select(PracticeAttempt).where(PracticeAttempt.question_id == rule.id)) is not None
