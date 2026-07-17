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


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("explicit null is not allowed")
        return value

    @field_validator("display_name")
    @classmethod
    def clean_optional_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("display_name cannot be blank")
        return value


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    foundation_level: Literal["basic", "intermediate", "advanced"] | None = None
    learning_order: Literal["explain_first", "weakness_first"] | None = None
    preferred_difficulty: Literal["basic", "adaptive", "advanced"] | None = None
    preferred_resource_types: list[Literal["pdf", "ppt", "markdown", "text"]] | None = None
    session_minutes: int | None = Field(default=None, ge=15, le=180)
    daily_minutes: int | None = Field(default=None, ge=15, le=720)
    needs_exam_focus: bool | None = None
    needs_error_points: bool | None = None
    needs_derivation: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("explicit null is not allowed")
        return value

    @field_validator("preferred_resource_types")
    @classmethod
    def deduplicate_resource_types(
        cls, value: list[Literal["pdf", "ppt", "markdown", "text"]] | None
    ) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(value))


class PreferenceRead(APIModel):
    foundation_level: Literal["basic", "intermediate", "advanced"]
    learning_order: Literal["explain_first", "weakness_first"]
    preferred_difficulty: Literal["basic", "adaptive", "advanced"]
    preferred_resource_types: list[Literal["pdf", "ppt", "markdown", "text"]]
    session_minutes: int
    daily_minutes: int
    needs_exam_focus: bool
    needs_error_points: bool
    needs_derivation: bool


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

    @field_validator("name")
    @classmethod
    def clean_optional_course_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


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
    daily_availability: dict[str, int] = Field(default_factory=dict)
    unavailable_dates: list[date] = Field(default_factory=list)
    session_minutes: int | None = Field(default=None, ge=15, le=180)
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
        default_minutes = self.daily_availability.get("default_minutes")
        if default_minutes is not None and not 15 <= default_minutes <= 720:
            raise ValueError("default_minutes must be between 15 and 720")
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


class DashboardCourseFocus(BaseModel):
    id: int
    name: str
    code: str | None
    exam_date: date | None
    days_until_exam: int | None
    has_active_plan: bool


class DashboardTodayTask(BaseModel):
    id: int
    course_id: int
    title: str
    task_type: str
    estimated_minutes: int
    actual_minutes: int | None
    priority: float
    difficulty: str
    status: str
    scheduled_date: date


class DashboardToday(BaseModel):
    items: list[DashboardTodayTask]
    total_count: int
    completed_count: int
    pending_count: int
    planned_minutes: int
    actual_minutes: int
    completion_rate: float


class DashboardMetrics(BaseModel):
    today_focus_minutes: int
    today_completion_rate: float
    average_mastery: float | None
    active_course_count: int
    ready_document_count: int
    study_days_in_range: int


class DashboardTrendPoint(BaseModel):
    date: date
    label: str
    learning_minutes: int
    scheduled_tasks: int
    completed_tasks: int
    completion_rate: float


class DashboardWeakPoint(BaseModel):
    knowledge_point_id: int
    knowledge_point: str
    course_id: int
    course_name: str
    score: float
    attempts: int
    confidence: float


class DashboardNextAction(BaseModel):
    type: str
    title: str
    reason: str
    route: str


class DashboardAsyncTask(BaseModel):
    task_id: str
    task_type: str
    status: str
    progress: int
    current_step: str | None
    created_at: datetime
    finished_at: datetime | None


class DashboardOverview(BaseModel):
    target_date: date
    range_start: date
    range_end: date
    timezone: str
    course_count: int
    ready_document_count: int
    focus_course: DashboardCourseFocus | None
    today: DashboardToday
    metrics: DashboardMetrics
    trend: list[DashboardTrendPoint]
    weak_points: list[DashboardWeakPoint]
    next_action: DashboardNextAction
    recent_async_tasks: list[DashboardAsyncTask]


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


class CourseRecommendationFeedback(BaseModel):
    recommendation_key: str = Field(min_length=1, max_length=160)
    action: Literal["clicked", "saved", "skipped"]


class AsyncTaskCreate(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    input_data: dict[str, Any] = Field(default_factory=dict)


class WeeklyReportInput(BaseModel):
    start_date: date
    end_date: date
    course_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> WeeklyReportInput:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if (self.end_date - self.start_date).days > 30:
            raise ValueError("date range must not exceed 31 days")
        return self


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
