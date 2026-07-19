from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from backend.app.database import Base

ID = BigInteger().with_variant(Integer, "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    preferences: Mapped[UserPreference | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    courses: Mapped[list[Course]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return self.display_name


class UserPreference(TimestampMixin, Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    foundation_level: Mapped[str] = mapped_column(String(24), default="basic")
    learning_order: Mapped[str] = mapped_column(String(24), default="explain_first")
    preferred_difficulty: Mapped[str] = mapped_column(String(24), default="basic")
    preferred_resource_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    session_minutes: Mapped[int] = mapped_column(Integer, default=45)
    daily_minutes: Mapped[int] = mapped_column(Integer, default=120)
    needs_exam_focus: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_error_points: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_derivation: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="preferences")


class Course(TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_course_owner_name"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_score: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner: Mapped[User] = relationship(back_populates="courses")
    documents: Mapped[list[Document]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    knowledge_points: Mapped[list[KnowledgePoint]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_course_status", "course_id", "status"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    course: Mapped[Course] = relationship(back_populates="documents")
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_document_version"),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="versions")


class DocumentChunk(TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "document_version", "chunk_index", name="uq_chunk_version_index"
        ),
        Index(
            "ix_chunks_course_document_version",
            "course_id",
            "document_id",
            "document_version",
        ),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    chapter_name: Mapped[str | None] = mapped_column(String(255))
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        JSON().with_variant(Vector(1024), "postgresql"), default=list, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")


class KnowledgePoint(TimestampMixin, Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_knowledge_course_name"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(24), default="basic", nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    prerequisite_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)

    course: Mapped[Course] = relationship(back_populates="knowledge_points")


class KnowledgeMastery(TimestampMixin, Base):
    __tablename__ = "knowledge_mastery"
    __table_args__ = (
        UniqueConstraint("user_id", "knowledge_point_id", name="uq_mastery_user_point"),
        Index("ix_mastery_user_course", "user_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.2, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_studied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), default="新对话", nullable=False)
    mode: Mapped[str] = mapped_column(String(24), default="strict", nullable=False)
    document_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(TimestampMixin, Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sufficient_evidence: Mapped[bool | None] = mapped_column(Boolean)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class StudyPlan(TimestampMixin, Base):
    __tablename__ = "study_plans"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    goal: Mapped[str] = mapped_column(String(500), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    active_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)

    versions: Mapped[list[StudyPlanVersion]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class StudyPlanVersion(TimestampMixin, Base):
    __tablename__ = "study_plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version", name="uq_plan_version"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="candidate", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    diff: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    plan: Mapped[StudyPlan] = relationship(back_populates="versions")
    tasks: Mapped[list[StudyTask]] = relationship(
        back_populates="plan_version", cascade="all, delete-orphan"
    )


class StudyTask(TimestampMixin, Base):
    __tablename__ = "study_tasks"
    __table_args__ = (Index("ix_tasks_user_date_status", "user_id", "scheduled_date", "status"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    plan_version_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan_versions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL")
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_minutes: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(24), default="basic", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="todo", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan_version: Mapped[StudyPlanVersion] = relationship(back_populates="tasks")


class LearningRecord(TimestampMixin, Base):
    __tablename__ = "learning_records"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_learning_records_task_id"),
    )

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("study_tasks.id", ondelete="SET NULL"))
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL")
    )
    record_type: Mapped[str] = mapped_column(String(32), default="study", nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PracticeQuestion(TimestampMixin, Base):
    __tablename__ = "practice_questions"
    __table_args__ = (UniqueConstraint("course_id", "seed_key", name="uq_practice_question_seed"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    knowledge_point_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_points.id", ondelete="SET NULL"))
    question_type: Mapped[str] = mapped_column(String(24), default="single_choice", nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list, nullable=False)
    correct_option: Mapped[str] = mapped_column(String(8), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(24), default="basic", nullable=False)
    origin: Mapped[str] = mapped_column(String(24), default="rule_seed", nullable=False)
    seed_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    source_page_number: Mapped[int | None] = mapped_column(Integer)
    source_quote: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PracticeAttempt(TimestampMixin, Base):
    __tablename__ = "practice_attempts"
    __table_args__ = (UniqueConstraint("user_id", "submission_id", name="uq_practice_attempt_submission"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("practice_questions.id", ondelete="CASCADE"), index=True)
    selected_option: Mapped[str] = mapped_column(String(8), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WrongQuestionEntry(TimestampMixin, Base):
    __tablename__ = "wrong_question_entries"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_wrong_question_user_question"),)

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("practice_questions.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    wrong_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_selected_option: Mapped[str] = mapped_column(String(8), nullable=False)
    last_wrong_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecommendationRecord(TimestampMixin, Base):
    __tablename__ = "recommendation_records"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    item_type: Mapped[str] = mapped_column(String(24), nullable=False)
    item_id: Mapped[int] = mapped_column(ID, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    score_breakdown: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="rule-v1")
    feedback_action: Mapped[str | None] = mapped_column(String(24))
    feedback_rating: Mapped[float | None] = mapped_column(Float)


class AsyncTask(TimestampMixin, Base):
    __tablename__ = "async_tasks"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str] = mapped_column(String(255), default="queued")
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MCPToolCall(TimestampMixin, Base):
    __tablename__ = "mcp_tool_calls"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    agent_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class CalendarEvent(TimestampMixin, Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(ID, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    study_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_tasks.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    remote_event_id: Mapped[str | None] = mapped_column(String(255))
    sync_status: Mapped[str] = mapped_column(String(24), default="local", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
