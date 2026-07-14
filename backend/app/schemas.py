from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=100)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("full_name cannot be blank")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(APIModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class CourseBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=5000)
    exam_date: date | None = None
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
    color: str | None = Field(default=None, max_length=20)
    archived: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_course_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class ExamDateUpdate(BaseModel):
    exam_date: date | None


class CourseRead(APIModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    code: str | None
    description: str | None
    exam_date: date | None
    color: str | None
    archived: bool
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str

