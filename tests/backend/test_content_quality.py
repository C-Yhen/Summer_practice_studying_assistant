from __future__ import annotations

from sqlalchemy import select

from backend.app.api.v1.plans import _persist_ai_points
from backend.app.models import Document, DocumentChunk, KnowledgePoint, PracticeQuestion


def _course(client, headers, name: str = "计算机组成原理") -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _source_backed_points(client, course_id: int) -> list[int]:
    """Create small course text where every point can be checked literally."""
    definitions = [
        ("存储器层次结构", "寄存器、Cache、主存和辅助存储器构成速度和容量不同的存储器层次结构。"),
        ("Cache命中率", "Cache命中率表示访问数据时在Cache中找到所需数据的比例，影响平均访问时间。"),
        ("直接寻址存储器", "直接寻址存储器可以按地址直接访问任意存储单元，访问时间与位置无关。"),
        ("主存与辅助存储器", "主存与辅助存储器中，主存用于CPU直接访问，辅助存储器容量大但访问速度较慢。"),
    ]
    with client.app.state.database.session_factory() as db:
        document = Document(course_id=course_id, title="存储器章节", file_type="txt", file_path="memory.txt", status="ready")
        db.add(document)
        db.flush()
        ids: list[int] = []
        for index, (name, content) in enumerate(definitions, start=1):
            db.add(DocumentChunk(
                document_id=document.id,
                course_id=course_id,
                document_version=1,
                chunk_index=index,
                content=content,
                page_number=index,
                chapter_name="第4章 存储器",
                embedding=[],
            ))
            point = KnowledgePoint(
                course_id=course_id,
                name=name,
                description=f"{content}\n来源：存储器章节 第{index}页。依据：{content}",
                importance=0.8,
                difficulty="basic",
                estimated_minutes=30,
            )
            db.add(point)
            db.flush()
            ids.append(point.id)
        # Historical pollution deliberately remains in the database.
        db.add_all([
            KnowledgePoint(course_id=course_id, name="核心概念", importance=0.9),
            KnowledgePoint(course_id=course_id, name="重点原理", importance=0.8),
            KnowledgePoint(course_id=course_id, name="综合应用", importance=0.7),
        ])
        db.commit()
        return ids


def test_real_points_persist_even_when_legacy_placeholders_exist(client, auth_headers) -> None:
    course_id = _course(client, auth_headers)
    _source_backed_points(client, course_id)
    source = "存储器层次结构由寄存器、Cache、主存和辅助存储器组成。"
    with client.app.state.database.session_factory() as db:
        saved = _persist_ai_points(db, course_id, [{
            "name": "Cache与主存映射",
            "description": "说明Cache如何保存主存块并减少平均访问时间。",
            "importance": 0.9,
            "difficulty": "intermediate",
            "estimated_minutes": 45,
            "source_quote": source,
            "source_text": source,
            "source_document_name": "存储器章节",
            "source_page_number": 1,
        }])
        db.commit()
        names = set(db.scalars(select(KnowledgePoint.name).where(KnowledgePoint.course_id == course_id)))
    assert saved and "Cache与主存映射" in names
    assert {"核心概念", "重点原理", "综合应用"}.issubset(names)


def test_plan_practice_and_recommendations_use_source_grounded_content(client, auth_headers) -> None:
    course_id = _course(client, auth_headers)
    _source_backed_points(client, course_id)
    with client.app.state.database.session_factory() as db:
        placeholder = db.scalar(select(KnowledgePoint).where(
            KnowledgePoint.course_id == course_id, KnowledgePoint.name == "核心概念"
        ))
        db.add(PracticeQuestion(
            course_id=course_id,
            knowledge_point_id=placeholder.id,
            seed_key="legacy-placeholder",
            stem="关于知识点“核心概念”，下列哪项最符合完成该知识点学习后的要求",
            options=[{"key": "A", "text": "只浏览任务标题即可"}],
            correct_option="A",
            explanation="legacy",
            origin="rule_seed",
            is_active=True,
        ))
        db.commit()

    boot = client.post(f"/api/v1/courses/{course_id}/practice/questions/bootstrap", headers=auth_headers)
    assert boot.status_code == 200
    questions = client.get(f"/api/v1/courses/{course_id}/practice/questions", headers=auth_headers).json()["data"]["items"]
    assert len(questions) >= 4
    assert len({item["stem"] for item in questions}) >= 4
    assert {item["correct_option"] for item in questions if "correct_option" in item} == set()  # hidden before an attempt
    with client.app.state.database.session_factory() as db:
        saved = list(db.scalars(select(PracticeQuestion).where(PracticeQuestion.course_id == course_id)))
        active = [item for item in saved if item.is_active]
        assert any(not item.is_active and item.seed_key == "legacy-placeholder" for item in saved)
        assert len({item.correct_option for item in active}) > 1
        assert all(item.source_quote and item.source_document_id and item.source_page_number for item in active)
        assert all("最符合完成该知识点学习后的要求" not in item.stem for item in active)

    generated = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=auth_headers,
        json={"goal": "复习存储器", "start_date": "2026-08-01", "end_date": "2026-08-06"},
    )
    assert generated.status_code == 200
    titles = [item["title"] for item in generated.json()["data"]["candidate_version"]["tasks"]]
    forbidden = ("核心概念", "重点原理", "综合应用", "阶段测试")
    assert titles and not any(token in title for title in titles for token in forbidden)
    assert all("“" in title and ("学习" in title or "复习" in title or "应用" in title) for title in titles)

    recommendations = client.get(
        f"/api/v1/courses/{course_id}/recommendations",
        headers=auth_headers,
        params={"target_date": "2026-08-01"},
    ).json()["data"]["items"]
    assert recommendations
    assert all(not any(token in item["title"] for token in forbidden[:3]) for item in recommendations)
    assert any(item["item_type"] == "mastery_review" and item["knowledge_point"] for item in recommendations)
