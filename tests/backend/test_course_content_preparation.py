from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import func, select

from backend.app.models import (
    AsyncTask,
    Course,
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgePoint,
    PracticeQuestion,
)
from backend.app.planning.ai_planner import (
    KnowledgePointExtractionError,
    extract_knowledge_points,
)
from backend.app.providers.llm import LLMProvider
from backend.app.services.ai_enrichment import (
    ensure_course_content_preparation,
    process_ai_enhancement,
)
from backend.app.services.course_content import (
    LEGACY_PLACEHOLDER_POINT_NAMES,
    course_content_readiness,
    ensure_grounded_rule_questions,
    persist_extracted_knowledge_points,
    primary_knowledge_points,
    question_has_exact_grounding,
)


SOURCE_TEXTS = [
    "系统总线由地址总线、数据总线和控制总线组成，各自承担不同的信息传输职责。",
    "总线仲裁用于决定多个主设备同时请求总线时的使用优先级和授权顺序。",
    "总线周期通常包含申请、寻址、传输和结束等阶段，时序约束保证设备协同。",
    "同步总线使用统一时钟协调传输，异步总线则通过请求与应答信号完成握手。",
    "总线带宽取决于总线宽度和工作频率，也会受到协议开销与等待周期影响。",
    "突发传输在一次寻址后连续传送多个数据单元，可以降低重复寻址带来的开销。",
]


class SequenceProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def chat(self, _messages, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

    async def embed(self, texts):
        return [[0.0] * 1024 for _ in texts]


def _source_rows(client, course_id: int, document_id: int) -> list[dict[str, object]]:
    with client.app.state.database.session_factory() as db:
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(
                    DocumentChunk.course_id == course_id,
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.document_version == 1,
                )
                .order_by(DocumentChunk.chunk_index)
            )
        )
    return [
        {
            "chunk_id": chunk.id,
            "document_id": document_id,
            "document_name": "系统总线讲义",
            "document_version": 1,
            "page_number": chunk.page_number,
            "chapter_name": chunk.chapter_name,
            "quote": chunk.content[:800],
            "score": 0.9,
        }
        for chunk in chunks
    ]


def _knowledge_payload() -> dict[str, object]:
    names = ["总线组成", "总线仲裁", "总线周期", "同步与异步总线", "总线带宽", "突发传输"]
    return {
        "knowledge_points": [
            {
                "name": name,
                "description": SOURCE_TEXTS[index - 1],
                "source_id": f"S{index}",
            }
            for index, name in enumerate(names, start=1)
        ]
    }


def _course(client, headers, name: str = "课程准备专项") -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _ready_document_with_chunks(client, course_id: int) -> int:
    with client.app.state.database.session_factory() as db:
        document = Document(
            course_id=course_id,
            title="系统总线讲义",
            file_type="pdf",
            file_path="system-bus.pdf",
            current_version=1,
            status="ready",
            page_count=len(SOURCE_TEXTS),
        )
        db.add(document)
        db.flush()
        db.add(
            DocumentVersion(
                document_id=document.id,
                version_no=1,
                file_path=document.file_path,
                status="ready",
                page_count=len(SOURCE_TEXTS),
                chunk_count=len(SOURCE_TEXTS),
            )
        )
        for index, text in enumerate(SOURCE_TEXTS, start=1):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    course_id=course_id,
                    document_version=1,
                    chunk_index=index - 1,
                    content=text,
                    page_number=index,
                    chapter_name="第3章 系统总线",
                    embedding=[0.0] * 1024,
                    is_active=True,
                )
            )
        db.commit()
        return document.id


def test_extraction_accepts_complete_json_fence_and_maps_source_ids(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "纯结构知识点")
    document_id = _ready_document_with_chunks(client, course_id)
    rows = _source_rows(client, course_id, document_id)

    async def sources(*_args, **_kwargs):
        return rows

    monkeypatch.setattr("backend.app.planning.ai_planner.retrieve", sources)
    payload = _knowledge_payload()
    payload["knowledge_points"][0]["quote_hint"] = "仅用于定位，不能保存为权威引用"
    provider = SequenceProvider(
        ["\ufeff  ```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```  "]
    )
    with client.app.state.database.session_factory() as db:
        points = asyncio.run(
            extract_knowledge_points(db, provider, course_id, [document_id])
        )

    assert len(points) == 6
    assert points[0]["source_document_id"] == document_id
    assert points[0]["source_page_number"] == 1
    assert points[0]["source_chunk_id"] == rows[0]["chunk_id"]
    assert points[0]["source_document_version"] == 1
    assert points[0]["source_quote"] in SOURCE_TEXTS[0]
    assert points[0]["source_quote"] != "仅用于定位，不能保存为权威引用"
    assert provider.calls[0]["enable_thinking"] is False
    assert provider.calls[0]["response_format"] == {"type": "json_object"}
    assert provider.calls[0]["_require_complete"] is True


def test_extraction_repairs_invalid_json_once(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "纠正结构")
    document_id = _ready_document_with_chunks(client, course_id)
    rows = _source_rows(client, course_id, document_id)

    async def sources(*_args, **_kwargs):
        return rows

    monkeypatch.setattr("backend.app.planning.ai_planner.retrieve", sources)
    provider = SequenceProvider(
        ["{\"knowledge_points\":[", json.dumps(_knowledge_payload(), ensure_ascii=False)]
    )
    with client.app.state.database.session_factory() as db:
        points = asyncio.run(
            extract_knowledge_points(db, provider, course_id, [document_id])
        )
    assert len(points) == 6
    assert len(provider.calls) == 2


def test_extraction_stops_after_two_invalid_json_responses(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "两次结构失败")
    document_id = _ready_document_with_chunks(client, course_id)
    rows = _source_rows(client, course_id, document_id)

    async def sources(*_args, **_kwargs):
        return rows

    monkeypatch.setattr("backend.app.planning.ai_planner.retrieve", sources)
    provider = SequenceProvider(["not json", "{\"knowledge_points\":["])
    with client.app.state.database.session_factory() as db:
        with pytest.raises(KnowledgePointExtractionError) as caught:
            asyncio.run(
                extract_knowledge_points(db, provider, course_id, [document_id])
            )
    assert caught.value.failure_type == "JSON_DECODE_FAILED"
    assert len(provider.calls) == 2


def test_extraction_rejects_unknown_source_id_without_repair_call(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "非法来源编号")
    document_id = _ready_document_with_chunks(client, course_id)
    rows = _source_rows(client, course_id, document_id)

    async def sources(*_args, **_kwargs):
        return rows

    payload = _knowledge_payload()
    payload["knowledge_points"][0]["source_id"] = "S99"
    monkeypatch.setattr("backend.app.planning.ai_planner.retrieve", sources)
    provider = SequenceProvider([json.dumps(payload, ensure_ascii=False)])
    with client.app.state.database.session_factory() as db:
        with pytest.raises(KnowledgePointExtractionError) as caught:
            asyncio.run(
                extract_knowledge_points(db, provider, course_id, [document_id])
            )
    assert caught.value.failure_type == "SOURCE_VALIDATION_FAILED"
    assert len(provider.calls) == 1


def test_extraction_rejects_semantically_unrelated_source(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "无关知识点")
    document_id = _ready_document_with_chunks(client, course_id)
    rows = _source_rows(client, course_id, document_id)

    async def sources(*_args, **_kwargs):
        return rows

    payload = _knowledge_payload()
    payload["knowledge_points"][0] = {
        "name": "总线组成",
        "description": "植物利用光能合成有机物并释放氧气。",
        "source_id": "S1",
    }
    monkeypatch.setattr("backend.app.planning.ai_planner.retrieve", sources)
    provider = SequenceProvider([json.dumps(payload, ensure_ascii=False)])
    with client.app.state.database.session_factory() as db:
        with pytest.raises(KnowledgePointExtractionError) as caught:
            asyncio.run(
                extract_knowledge_points(db, provider, course_id, [document_id])
            )
    assert caught.value.failure_type == "SOURCE_VALIDATION_FAILED"
    assert len(provider.calls) == 1


def test_model_source_quote_is_rejected_then_backend_derives_exact_quote(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "模型伪造引用")
    document_id = _ready_document_with_chunks(client, course_id)
    rows = _source_rows(client, course_id, document_id)

    async def sources(*_args, **_kwargs):
        return rows

    forged = _knowledge_payload()
    for point in forged["knowledge_points"]:
        point["source_quote"] = "模型自行生成的引用，不能作为真实性证据。"
    provider = SequenceProvider(
        [
            json.dumps(forged, ensure_ascii=False),
            json.dumps(_knowledge_payload(), ensure_ascii=False),
        ]
    )
    monkeypatch.setattr("backend.app.planning.ai_planner.retrieve", sources)
    with client.app.state.database.session_factory() as db:
        points = asyncio.run(
            extract_knowledge_points(db, provider, course_id, [document_id])
        )
    assert len(provider.calls) == 2
    assert all(
        item["source_quote"] in item["source_text"]
        and item["source_quote"] != "模型自行生成的引用，不能作为真实性证据。"
        for item in points
    )


def test_course_preparation_persists_points_questions_and_ready_state(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers)
    document_id = _ready_document_with_chunks(client, course_id)
    client.app.state.settings.llm_provider = "fake"
    monkeypatch.setattr(
        "backend.app.services.ai_enrichment.dispatch_async_task",
        lambda *_args, **_kwargs: asyncio.sleep(0),
    )

    async def extracted(*_args, **_kwargs):
        rows = _source_rows(client, course_id, document_id)
        result = []
        for index, item in enumerate(_knowledge_payload()["knowledge_points"]):
            source = rows[index]
            result.append(
                {
                    **item,
                    "source_document_id": document_id,
                    "source_document_name": source["document_name"],
                    "source_page_number": source["page_number"],
                    "source_chunk_id": source["chunk_id"],
                    "source_text": source["quote"],
                    "source_quote": source["quote"],
                }
            )
        return result

    monkeypatch.setattr(
        "backend.app.services.ai_enrichment.get_llm_provider", lambda _settings: object()
    )
    monkeypatch.setattr(
        "backend.app.services.ai_enrichment.extract_knowledge_points", extracted
    )
    with client.app.state.database.session_factory() as db:
        owner_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        task = asyncio.run(
            ensure_course_content_preparation(
                db,
                client.app.state.settings,
                user_id=owner_id,
                course_id=course_id,
                allow_retry=False,
            )
        )
        assert task is not None
        result = asyncio.run(process_ai_enhancement(db, task, client.app.state.settings))
        db.refresh(task)
        readiness = course_content_readiness(db, course_id, user_id=owner_id)
        assert task.status == "success"
        assert result["knowledge_point_count"] == 6
        assert result["question_count"] >= 6
        assert readiness["status"] == "ready"
        assert readiness["ready"] is True
        assert db.scalar(
            select(func.count(KnowledgePoint.id)).where(KnowledgePoint.course_id == course_id)
        ) == 6
        questions = list(
            db.scalars(
                select(PracticeQuestion).where(
                    PracticeQuestion.course_id == course_id,
                    PracticeQuestion.is_active.is_(True),
                )
            )
        )
        assert len(questions) >= 6
        assert len({item.stem for item in questions}) >= 6
        assert len({item.correct_option for item in questions}) > 1
        assert all(item.source_quote and item.source_document_id for item in questions)


def test_question_quotes_preserve_raw_whitespace_and_gate_ready(
    client, auth_headers
) -> None:
    course_id = _course(client, auth_headers, "原文空白保持")
    document_id = _ready_document_with_chunks(client, course_id)
    raw_source = "系统总线包含地址总线、\n  数据总线和控制总线，三者承担不同职责。"
    with client.app.state.database.session_factory() as db:
        first_chunk = db.scalar(
            select(DocumentChunk).where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_index == 0,
            )
        )
        first_chunk.content = raw_source
        sources = [raw_source, *SOURCE_TEXTS[1:]]
        names = ["系统总线组成", "总线仲裁", "总线周期", "异步总线", "总线带宽", "突发传输"]
        persist_extracted_knowledge_points(
            db,
            course_id,
            [
                {
                    "name": name,
                    "description": f"{name}的具体课程说明",
                    "source_document_name": "系统总线讲义",
                    "source_page_number": index,
                    "source_text": sources[index - 1],
                    "source_quote": sources[index - 1],
                    "importance": 0.8,
                    "estimated_minutes": 45,
                }
                for index, name in enumerate(names, start=1)
            ],
        )
        prepared = ensure_grounded_rule_questions(db, course_id)
        db.commit()
        questions = list(
            db.scalars(
                select(PracticeQuestion)
                .where(
                    PracticeQuestion.course_id == course_id,
                    PracticeQuestion.is_active.is_(True),
                )
                .order_by(PracticeQuestion.id)
            )
        )
        owner_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        initial = course_content_readiness(db, course_id, user_id=owner_id)

        assert prepared["question_count"] == 6
        assert "\n  " in questions[0].source_quote
        assert questions[0].source_quote in first_chunk.content
        assert initial["ready"] is True
        assert initial["invalid_question_count"] == 0

        original_question_id = questions[0].id
        questions[0].source_quote = " ".join(questions[0].source_quote.split())
        db.commit()
        folded = course_content_readiness(db, course_id, user_id=owner_id)
        assert folded["ready"] is False
        assert folded["invalid_question_count"] == 1

        repaired = ensure_grounded_rule_questions(db, course_id)
        db.commit()
        final = course_content_readiness(db, course_id, user_id=owner_id)
        active_questions = list(
            db.scalars(
                select(PracticeQuestion).where(
                    PracticeQuestion.course_id == course_id,
                    PracticeQuestion.is_active.is_(True),
                )
            )
        )
        old_question = db.get(PracticeQuestion, original_question_id)

        assert repaired["created_count"] == 1
        assert old_question.is_active is False
        assert final["ready"] is True
        assert final["invalid_question_count"] == 0
        assert all(
            question_has_exact_grounding(db, question)
            for question in active_questions
        )


def test_only_twelve_deduplicated_primary_points_feed_questions(
    client, auth_headers
) -> None:
    course_id = _course(client, auth_headers, "主要知识点上限")
    document_id = _ready_document_with_chunks(client, course_id)
    with client.app.state.database.session_factory() as db:
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        raw_points = []
        for index in range(14):
            chunk = chunks[index % len(chunks)]
            raw_points.append(
                {
                    "name": f"总线知识点{index + 1}",
                    "description": f"第{index + 1}个真实总线知识点",
                    "source_document_name": "系统总线讲义",
                    "source_page_number": chunk.page_number,
                    "source_text": chunk.content,
                    "source_quote": chunk.content,
                    "importance": 0.8,
                    "estimated_minutes": 45,
                }
            )
        persist_extracted_knowledge_points(db, course_id, raw_points)
        prepared = ensure_grounded_rule_questions(db, course_id)
        db.commit()

        assert len(primary_knowledge_points(db, course_id)) == 12
        assert db.scalar(
            select(func.count(KnowledgePoint.id)).where(
                KnowledgePoint.course_id == course_id
            )
        ) == 14
        assert prepared["question_count"] == 12
        assert db.scalar(
            select(func.count(PracticeQuestion.id)).where(
                PracticeQuestion.course_id == course_id,
                PracticeQuestion.is_active.is_(True),
            )
        ) == 12


def test_placeholder_questions_never_make_a_course_ready(
    client, auth_headers
) -> None:
    course_id = _course(client, auth_headers, "历史占位题不算就绪")
    document_id = _ready_document_with_chunks(client, course_id)
    with client.app.state.database.session_factory() as db:
        point = KnowledgePoint(
            course_id=course_id,
            name=next(iter(LEGACY_PLACEHOLDER_POINT_NAMES)),
            description="legacy placeholder",
            difficulty="basic",
            estimated_minutes=30,
        )
        db.add(point)
        db.flush()
        db.add(
            PracticeQuestion(
                course_id=course_id,
                knowledge_point_id=point.id,
                stem="legacy placeholder question",
                options=[{"key": key, "text": key} for key in "ABCD"],
                correct_option="A",
                explanation="legacy",
                seed_key=f"legacy:{point.id}",
                source_document_id=document_id,
                source_page_number=1,
                source_quote=SOURCE_TEXTS[0],
                is_active=True,
            )
        )
        db.commit()
        owner_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        readiness = course_content_readiness(db, course_id, user_id=owner_id)

    assert readiness["ready"] is False
    assert readiness["knowledge_point_count"] == 0
    assert readiness["question_count"] == 0


def test_failed_preparation_is_reused_until_explicit_retry(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "课程准备显式重试")
    _ready_document_with_chunks(client, course_id)
    client.app.state.settings.llm_provider = "fake"
    monkeypatch.setattr(
        "backend.app.services.ai_enrichment.dispatch_async_task",
        lambda *_args, **_kwargs: asyncio.sleep(0),
    )
    with client.app.state.database.session_factory() as db:
        owner_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        first = asyncio.run(
            ensure_course_content_preparation(
                db,
                client.app.state.settings,
                user_id=owner_id,
                course_id=course_id,
                allow_retry=False,
            )
        )
        first.status = "failed"
        first.error_message = "JSON_DECODE_FAILED"
        db.commit()
        passive = asyncio.run(
            ensure_course_content_preparation(
                db,
                client.app.state.settings,
                user_id=owner_id,
                course_id=course_id,
                allow_retry=False,
            )
        )
        explicit = asyncio.run(
            ensure_course_content_preparation(
                db,
                client.app.state.settings,
                user_id=owner_id,
                course_id=course_id,
                allow_retry=True,
            )
        )
        assert passive.id == first.id
        assert explicit.id != first.id
        assert explicit.status == "queued"


def test_document_completion_auto_queues_one_preparation_and_blocks_consumers(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "文档完成自动准备")
    client.app.state.settings.llm_provider = "fake"
    dispatched: list[str] = []

    class EmbeddingProvider(LLMProvider):
        async def chat(self, _messages, **_kwargs):
            raise AssertionError("document parsing must not call chat inline")

        async def embed(self, texts):
            return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr(
        "backend.app.providers.llm.get_llm_provider",
        lambda _settings: EmbeddingProvider(),
    )
    monkeypatch.setattr(
        "backend.app.tasks.jobs.process_ai_enhancement_job.delay",
        lambda task_id: dispatched.append(task_id),
    )

    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        headers=auth_headers,
        files={
            "file": (
                "系统总线.txt",
                "\n".join(SOURCE_TEXTS).encode(),
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201
    with client.app.state.database.session_factory() as db:
        tasks = list(
            db.scalars(
                select(AsyncTask).where(
                    AsyncTask.resource_type == "course",
                    AsyncTask.resource_id == str(course_id),
                    AsyncTask.task_type == "knowledge_point_extraction",
                )
            )
        )
        assert len(tasks) == 1
        assert dispatched == [tasks[0].public_id]

    readiness = client.get(
        f"/api/v1/courses/{course_id}/content-readiness", headers=auth_headers
    )
    assert readiness.status_code == 200
    assert readiness.json()["data"]["status"] == "processing"
    assert readiness.json()["data"]["task_id"] == dispatched[0]

    plan = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=auth_headers,
        json={
            "goal": "学习系统总线",
            "start_date": "2026-08-01",
            "end_date": "2026-08-07",
        },
    )
    assert plan.status_code == 409
    assert plan.json()["detail"].startswith("COURSE_CONTENT_PREPARING:")
    practice = client.post(
        f"/api/v1/courses/{course_id}/practice/questions/bootstrap",
        headers=auth_headers,
    )
    assert practice.status_code == 200
    assert practice.json()["data"]["reason"] == "COURSE_CONTENT_PREPARING"


def test_course_preparation_waits_until_all_current_documents_are_ready(
    client, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    course_id = _course(client, auth_headers, "多文档课程准备")
    first_id = _ready_document_with_chunks(client, course_id)
    client.app.state.settings.llm_provider = "fake"
    monkeypatch.setattr(
        "backend.app.services.ai_enrichment.dispatch_async_task",
        lambda *_args, **_kwargs: asyncio.sleep(0),
    )
    with client.app.state.database.session_factory() as db:
        owner_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        second = Document(
            course_id=course_id,
            title="仍在向量化的资料",
            file_type="txt",
            file_path="pending.txt",
            status="embedding",
        )
        db.add(second)
        db.flush()
        db.add(
            DocumentVersion(
                document_id=second.id,
                version_no=1,
                file_path=second.file_path,
                status="embedding",
            )
        )
        db.commit()
        assert (
            asyncio.run(
                ensure_course_content_preparation(
                    db,
                    client.app.state.settings,
                    user_id=owner_id,
                    course_id=course_id,
                    allow_retry=False,
                )
            )
            is None
        )
        second.status = "ready"
        version = db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == second.id)
        )
        version.status = "ready"
        db.add(
            DocumentChunk(
                document_id=second.id,
                course_id=course_id,
                document_version=1,
                chunk_index=0,
                content="第二份资料已经完成向量化。",
                page_number=1,
                embedding=[0.0] * 1024,
            )
        )
        db.commit()
        task = asyncio.run(
            ensure_course_content_preparation(
                db,
                client.app.state.settings,
                user_id=owner_id,
                course_id=course_id,
                allow_retry=False,
            )
        )
        assert task is not None
        assert task.input_data["document_ids"] == [first_id, second.id]
