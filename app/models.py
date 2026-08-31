from __future__ import annotations

import enum
import uuid
import datetime as dt
from typing import List, Optional

from sqlalchemy import (
    String,
    Text,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
    JSON,
    func,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Gender(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class UserRole(str, enum.Enum):
    employee = "employee"
    hr = "hr"
    admin = "admin"


class QuestionType(str, enum.Enum):
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"


class AttemptStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    canceled = "canceled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    id_max: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    gender: Mapped[Optional[Gender]] = mapped_column(
        SAEnum(Gender, native_enum=False, length=20),
        nullable=True,
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, native_enum=False, length=20),
        default=UserRole.employee,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bucket: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(1024), index=True)
    original_filename: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, default=0)

    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("parent_id <> id", name="ck_category_parent_not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    parent: Mapped[Optional["Category"]] = relationship(
        "Category",
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[List["Category"]] = relationship(
        "Category",
        back_populates="parent",
    )
    materials: Mapped[List["Material"]] = relationship(
        "Material",
        back_populates="category",
    )


class Test(Base):
    __tablename__ = "tests"
    __table_args__ = (
        CheckConstraint("passing_score >= 0", name="ck_tests_passing_score_nonnegative"),
        CheckConstraint("max_score >= 0", name="ck_tests_max_score_nonnegative"),
        CheckConstraint(
            "max_attempts IS NULL OR max_attempts > 0",
            name="ck_tests_max_attempts_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    title: Mapped[str] = mapped_column(String(255))
    topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    passing_score: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer, default=0)

    max_attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retake_interval_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    questions: Mapped[List["TestQuestion"]] = relationship(
        "TestQuestion",
        back_populates="test",
        cascade="all, delete-orphan",
    )
    grades: Mapped[List["TestGrade"]] = relationship(
        "TestGrade",
        back_populates="test",
        cascade="all, delete-orphan",
    )
    attempts: Mapped[List["TestAttempt"]] = relationship(
        "TestAttempt",
        back_populates="test",
    )
    materials_attached: Mapped[List["Material"]] = relationship(
        "Material",
        back_populates="test",
    )


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint(
            "file_id IS NOT NULL OR external_url IS NOT NULL",
            name="ck_material_has_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    external_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)

    file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
    )

    test_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tests.id", ondelete="SET NULL"),
        nullable=True,
    )

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped["Category"] = relationship(
        "Category",
        back_populates="materials",
    )
    file: Mapped[Optional["File"]] = relationship("File")
    test: Mapped[Optional["Test"]] = relationship(
        "Test",
        back_populates="materials_attached",
    )
    views: Mapped[List["MaterialView"]] = relationship(
        "MaterialView",
        back_populates="material",
        cascade="all, delete-orphan",
    )


class TestQuestion(Base):
    __tablename__ = "test_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(
        SAEnum(QuestionType, native_enum=False, length=30),
        default=QuestionType.single_choice,
    )

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    test: Mapped["Test"] = relationship(
        "Test",
        back_populates="questions",
    )
    answers: Mapped[List["TestAnswerOption"]] = relationship(
        "TestAnswerOption",
        back_populates="question",
        cascade="all, delete-orphan",
    )


class TestAnswerOption(Base):
    __tablename__ = "test_answer_options"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    text: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    question: Mapped["TestQuestion"] = relationship(
        "TestQuestion",
        back_populates="answers",
    )


class TestGrade(Base):
    __tablename__ = "test_grades"
    __table_args__ = (
        CheckConstraint("min_score >= 0", name="ck_test_grades_min_score_nonnegative"),
        CheckConstraint(
            "max_score IS NULL OR max_score >= min_score",
            name="ck_test_grades_max_score_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255))
    min_score: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    test: Mapped["Test"] = relationship(
        "Test",
        back_populates="grades",
    )


class TestAttempt(Base):
    __tablename__ = "test_attempts"
    __table_args__ = (
        Index("ix_test_attempts_user_test", "user_id", "test_id"),
        CheckConstraint(
            "score IS NULL OR score >= 0",
            name="ck_test_attempts_score_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[AttemptStatus] = mapped_column(
        SAEnum(AttemptStatus, native_enum=False, length=30),
        default=AttemptStatus.in_progress,
    )

    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passing_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    grade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("test_grades.id", ondelete="SET NULL"),
        nullable=True,
    )
    grade_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    attempt_number: Mapped[int] = mapped_column(Integer, default=1)

    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    test: Mapped["Test"] = relationship(
        "Test",
        back_populates="attempts",
    )
    user: Mapped["User"] = relationship("User")
    grade: Mapped[Optional["TestGrade"]] = relationship("TestGrade")

    answers: Mapped[List["TestAttemptAnswer"]] = relationship(
        "TestAttemptAnswer",
        back_populates="attempt",
        cascade="all, delete-orphan",
    )


class TestAttemptAnswer(Base):
    __tablename__ = "test_attempt_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_questions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    selected_option_ids: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    attempt: Mapped["TestAttempt"] = relationship(
        "TestAttempt",
        back_populates="answers",
    )
    question: Mapped["TestQuestion"] = relationship("TestQuestion")


class MaterialView(Base):
    __tablename__ = "material_views"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    viewed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    material: Mapped["Material"] = relationship(
        "Material",
        back_populates="views",
    )
    user: Mapped[Optional["User"]] = relationship("User")