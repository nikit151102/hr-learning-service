from __future__ import annotations

from datetime import datetime
from typing import Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import AttemptStatus, Gender, QuestionType, UserRole


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int


# Auth / users

class LoginRequest(BaseModel):
    id_max: str


class UserCreate(BaseModel):
    id_max: str = Field(min_length=1, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    gender: Optional[Gender] = None
    role: UserRole = UserRole.employee


class UserUpdate(BaseModel):
    id_max: Optional[str] = None
    full_name: Optional[str] = None
    gender: Optional[Gender] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    id_max: str
    full_name: str
    gender: Optional[Gender]
    role: UserRole
    is_active: bool
    created_at: datetime


# Categories

class CategoryCreate(BaseModel):
    parent_id: Optional[UUID] = None
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    parent_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parent_id: Optional[UUID]
    name: str
    description: Optional[str]
    sort_order: int
    created_at: datetime


class CategoryTree(CategoryRead):
    children: List["CategoryTree"] = []


CategoryTree.model_rebuild()


# Files

class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bucket: str
    object_key: str
    original_filename: str
    content_type: str
    size: int
    created_at: datetime


# Tests

class TestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    topic: Optional[str]
    passing_score: int
    max_score: int
    max_attempts: Optional[int]
    is_published: bool


class TestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    topic: Optional[str] = None
    description: Optional[str] = None
    passing_score: int = Field(default=0, ge=0)
    max_attempts: Optional[int] = Field(default=None, ge=1)
    retake_interval_minutes: Optional[int] = Field(default=None, ge=0)
    shuffle_questions: bool = False


class TestUpdate(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    passing_score: Optional[int] = Field(default=None, ge=0)
    max_attempts: Optional[int] = Field(default=None, ge=1)
    retake_interval_minutes: Optional[int] = Field(default=None, ge=0)
    shuffle_questions: Optional[bool] = None
    is_published: Optional[bool] = None


class TestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    topic: Optional[str]
    description: Optional[str]
    passing_score: int
    max_score: int
    max_attempts: Optional[int]
    retake_interval_minutes: Optional[int]
    shuffle_questions: bool
    is_published: bool
    created_at: datetime


class AnswerOptionCreate(BaseModel):
    text: str
    score: int = 0
    sort_order: int = 0
    is_active: bool = True


class AnswerOptionUpdate(BaseModel):
    text: Optional[str] = None
    score: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class AnswerOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str
    score: int
    sort_order: int
    is_active: bool


class QuestionCreate(BaseModel):
    text: str
    question_type: QuestionType = QuestionType.single_choice
    sort_order: int = 0
    is_active: bool = True
    answers: List[AnswerOptionCreate] = []


class QuestionUpdate(BaseModel):
    text: Optional[str] = None
    question_type: Optional[QuestionType] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_id: UUID
    text: str
    question_type: QuestionType
    sort_order: int
    max_score: int
    is_active: bool
    answers: List[AnswerOptionRead] = []


class GradeCreate(BaseModel):
    name: str
    min_score: int = Field(ge=0)
    max_score: Optional[int] = Field(default=None, ge=0)
    description: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0

    @model_validator(mode="after")
    def validate_max(self):
        if self.max_score is not None and self.max_score < self.min_score:
            raise ValueError("max_score must be >= min_score")
        return self


class GradeUpdate(BaseModel):
    name: Optional[str] = None
    min_score: Optional[int] = Field(default=None, ge=0)
    max_score: Optional[int] = Field(default=None, ge=0)
    description: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class GradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_id: UUID
    name: str
    min_score: int
    max_score: Optional[int]
    description: Optional[str]
    color: Optional[str]
    sort_order: int


class TestFullRead(TestRead):
    questions: List[QuestionRead] = []
    grades: List[GradeRead] = []


# Materials

class MaterialCreate(BaseModel):
    category_id: UUID
    title: str
    description: Optional[str] = None

    external_url: Optional[str] = None
    file_id: Optional[UUID] = None
    test_id: Optional[UUID] = None

    sort_order: int = 0
    is_published: bool = True

    @model_validator(mode="after")
    def validate_source(self):
        has_file = bool(self.file_id)
        has_url = bool(self.external_url)

        if has_file == has_url:
            raise ValueError("Material must have exactly one source: file_id or external_url")

        return self


class MaterialUpdate(BaseModel):
    category_id: Optional[UUID] = None
    title: Optional[str] = None
    description: Optional[str] = None

    external_url: Optional[str] = None
    file_id: Optional[UUID] = None
    test_id: Optional[UUID] = None

    sort_order: Optional[int] = None
    is_published: Optional[bool] = None


class MaterialSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    category_id: UUID
    external_url: Optional[str]
    file_id: Optional[UUID]
    test_id: Optional[UUID]
    is_published: bool
    sort_order: int


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    title: str
    description: Optional[str]
    external_url: Optional[str]
    file_id: Optional[UUID]
    test_id: Optional[UUID]
    sort_order: int
    is_published: bool
    view_count: int
    created_at: datetime

    file: Optional[FileRead] = None
    test: Optional[TestSummary] = None


class MaterialReadWithUrl(MaterialRead):
    download_url: Optional[str] = None


class CategoryContents(BaseModel):
    category: CategoryRead
    subcategories: List[CategoryRead]
    materials: Page[MaterialSummary]


# Attempts

class AnswerOptionPublic(BaseModel):
    id: UUID
    text: str


class QuestionPublic(BaseModel):
    id: UUID
    text: str
    question_type: QuestionType
    answers: List[AnswerOptionPublic]


class AttemptStartRead(BaseModel):
    id: UUID
    test_id: UUID
    attempt_number: int
    max_score: int
    passing_score: int
    questions: List[QuestionPublic]


class AttemptAnswerSubmit(BaseModel):
    question_id: UUID
    selected_option_ids: List[UUID] = []


class AttemptSubmit(BaseModel):
    answers: List[AttemptAnswerSubmit]


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_id: UUID
    user_id: UUID
    status: AttemptStatus
    score: Optional[int]
    max_score: Optional[int]
    passing_score: Optional[int]
    passed: Optional[bool]
    grade_id: Optional[UUID]
    grade_name: Optional[str]
    attempt_number: int
    started_at: datetime
    completed_at: Optional[datetime]


class AttemptAccess(BaseModel):
    can_start: bool
    reason: str
    completed_attempts: int
    attempts_left: Optional[int]
    cooldown_until: Optional[datetime]