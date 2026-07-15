from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("display_name", "full_name", "name"),
    )

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("display_name cannot be blank")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(APIModel):
    id: int
    email: EmailStr
    display_name: str
    full_name: str
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class PreferenceUpdate(BaseModel):
    foundation_level: str = Field(default="basic", max_length=24)
    learning_order: str = Field(default="explain_first", max_length=24)
    preferred_difficulty: str = Field(default="basic", max_length=24)
    preferred_resource_types: list[str] = Field(default_factory=list)
    session_minutes: int = Field(default=45, ge=15, le=180)
    daily_minutes: int = Field(default=120, ge=15, le=720)
    needs_exam_focus: bool = True
    needs_error_points: bool = True
    needs_derivation: bool = False


class CourseBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=5000)
    exam_date: date | None = None
    target_score: int = Field(default=85, ge=0, le=100)
    color: str | None = Field(default=None, max_length=20)
    archived: bool = False

    @field_validator("name")
    @classmethod
    def clean_course_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=5000)
    exam_date: date | None = None
    target_score: int | None = Field(default=None, ge=0, le=100)
    color: str | None = Field(default=None, max_length=20)
    archived: bool | None = None


class ExamDateUpdate(BaseModel):
    exam_date: date | None = None
    exam_at: datetime | None = None

    def resolved_date(self) -> date | None:
        return self.exam_date or (self.exam_at.date() if self.exam_at else None)


class CourseRead(APIModel):
    id: int
    owner_id: int
    name: str
    code: str | None
    description: str | None
    exam_date: date | None
    target_score: int
    color: str | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class DocumentRead(APIModel):
    id: int
    course_id: int
    title: str
    file_type: str
    current_version: int
    status: str
    page_count: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ChatSessionCreate(BaseModel):
    title: str = Field(default="新对话", max_length=255)
    mode: Literal["basic", "exam", "strict", "teacher"] = "strict"
    document_ids: list[int] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def clean_chat_title(cls, value: str) -> str:
        return value.strip() or "新对话"


class ChatSessionRead(BaseModel):
    session_id: str
    course_id: int
    title: str
    mode: str
    document_ids: list[int]
    created_at: datetime
    updated_at: datetime


class RagCitationRead(BaseModel):
    source_id: str
    chunk_id: int
    document_id: int
    document_name: str
    document_version: int
    page_number: int | None
    chapter_name: str | None
    quote: str
    score: float


class ChatMessageRead(BaseModel):
    id: str
    role: str
    content: str
    citations: list[RagCitationRead]
    sufficient_evidence: bool | None
    created_at: datetime


class ChatAsk(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: Literal["basic", "exam", "strict", "teacher"] | None = None
    document_ids: list[int] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question cannot be blank")
        return value


class RagSearch(BaseModel):
    course_id: int
    query: str = Field(min_length=1, max_length=4000)
    document_ids: list[int] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)
    strict: bool = True

    @field_validator("query")
    @classmethod
    def clean_rag_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query cannot be blank")
        return value


class PlanGenerate(BaseModel):
    start_date: date
    end_date: date
    daily_availability: dict[str, int] = Field(default_factory=lambda: {"default_minutes": 120})
    unavailable_dates: list[date] = Field(default_factory=list)
    session_minutes: int = Field(default=45, ge=15, le=180)
    goal: str = Field(default="完成课程复习", max_length=500)

    @model_validator(mode="after")
    def validate_dates(self) -> PlanGenerate:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if (self.end_date - self.start_date).days > 180:
            raise ValueError("plan date range must not exceed 180 days")
        self.goal = self.goal.strip()
        if not self.goal:
            raise ValueError("goal cannot be blank")
        default_minutes = self.daily_availability.get("default_minutes", 120)
        if not 15 <= default_minutes <= 720:
            raise ValueError("default_minutes must be between 15 and 720")
        if self.session_minutes > default_minutes:
            raise ValueError("session_minutes must not exceed default_minutes")
        for raw_date, minutes in self.daily_availability.items():
            if raw_date == "default_minutes":
                continue
            try:
                override_date = date.fromisoformat(raw_date)
            except ValueError as exc:
                raise ValueError(f"daily availability date is invalid: {raw_date}") from exc
            if not self.start_date <= override_date <= self.end_date:
                raise ValueError("daily availability date must be within plan range")
            if not 0 <= minutes <= 720:
                raise ValueError("daily availability minutes must be between 0 and 720")
        if any(day < self.start_date or day > self.end_date for day in self.unavailable_dates):
            raise ValueError("unavailable_dates must be within plan range")
        return self


class AdjustmentCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    constraints: dict[str, Any] = Field(default_factory=dict)
    base_version: int = Field(ge=1)


class PlanConfirm(BaseModel):
    expected_base_version: int = Field(ge=0)
    confirmation_token: str = Field(min_length=10)


class TaskComplete(BaseModel):
    actual_minutes: int = Field(ge=1, le=1440)
    completed_at: datetime | None = None


class LearningRecordCreate(BaseModel):
    course_id: int
    task_id: int | None = None
    knowledge_point_id: int | None = None
    duration_seconds: int = Field(ge=1, le=86400)
    record_type: str = Field(default="study", max_length=32)
    completed: bool = False
    occurred_at: datetime | None = None


class RecommendationFeedback(BaseModel):
    action: Literal["shown", "clicked", "completed", "skipped", "saved"]
    rating: float | None = Field(default=None, ge=1, le=5)


class AsyncTaskCreate(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    resource_type: str | None = Field(default=None, max_length=32)
    resource_id: str | None = Field(default=None, max_length=64)
    input_data: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallCreate(BaseModel):
    user_id: int | None = None
    agent_run_id: str = Field(min_length=1, max_length=64)
    tool_name: str = Field(min_length=1, max_length=100)
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] | None = None
    status: str = Field(max_length=24)
    error_message: str | None = None
    duration_ms: float = Field(default=0, ge=0)


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    study_task_id: int | None = None
    idempotency_key: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_range(self) -> CalendarEventCreate:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
