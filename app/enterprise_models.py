from __future__ import annotations

import enum
import uuid
import datetime as dt
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class CourseEnrollmentStatus(str, enum.Enum):
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    canceled = "canceled"


class NotificationType(str, enum.Enum):
    info = "info"
    assignment_created = "assignment_created"
    course_assigned = "course_assigned"
    due_soon = "due_soon"
    overdue = "overdue"
    test_passed = "test_passed"
    test_failed = "test_failed"
    certificate_issued = "certificate_issued"
    course_completed = "course_completed"


class ManagerRight(Base):
    __tablename__ = "manager_rights"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    department: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User")


class EmployeeDepartment(Base):
    __tablename__ = "employee_departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    department: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship("User")


class MandatoryTest(Base):
    __tablename__ = "mandatory_tests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tests.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    test: Mapped["Test"] = relationship("Test")
    creator: Mapped[Optional["User"]] = relationship("User")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)

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

    items: Mapped[list["CourseItem"]] = relationship(
        "CourseItem",
        back_populates="course",
        cascade="all, delete-orphan",
    )

    enrollments: Mapped[list["CourseEnrollment"]] = relationship(
        "CourseEnrollment",
        back_populates="course",
    )


class CourseItem(Base):
    __tablename__ = "course_items"
    __table_args__ = (
        CheckConstraint(
            """
            (material_id IS NOT NULL AND test_id IS NULL)
            OR
            (material_id IS NULL AND test_id IS NOT NULL)
            """,
            name="ck_course_item_object",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    material_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    test_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    course: Mapped["Course"] = relationship(
        "Course",
        back_populates="items",
    )

    material: Mapped[Optional["Material"]] = relationship("Material")
    test: Mapped[Optional["Test"]] = relationship("Test")


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_course_enrollment_user"),
        Index("ix_course_enrollments_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[CourseEnrollmentStatus] = mapped_column(
        SAEnum(CourseEnrollmentStatus, native_enum=False, length=30),
        default=CourseEnrollmentStatus.assigned,
    )

    due_date: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    progress_percent: Mapped[int] = mapped_column(Integer, default=0)

    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    course: Mapped["Course"] = relationship(
        "Course",
        back_populates="enrollments",
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    assigned_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[assigned_by],
    )

    progress: Mapped[list["CourseItemProgress"]] = relationship(
        "CourseItemProgress",
        back_populates="enrollment",
        cascade="all, delete-orphan",
    )


class CourseItemProgress(Base):
    __tablename__ = "course_item_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "item_id", name="uq_course_item_progress"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("course_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    completed_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
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

    enrollment: Mapped["CourseEnrollment"] = relationship(
        "CourseEnrollment",
        back_populates="progress",
    )

    item: Mapped["CourseItem"] = relationship("CourseItem")


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        CheckConstraint(
            """
            (course_id IS NOT NULL AND test_id IS NULL)
            OR
            (course_id IS NULL AND test_id IS NOT NULL)
            """,
            name="ck_certificate_object",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    certificate_number: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    test_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    issued_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    pdf_bucket: Mapped[str] = mapped_column(String(255))
    pdf_object_key: Mapped[str] = mapped_column(String(1024))

    revoked_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    revoke_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ВАЖНО: явно указываем, какой FK использовать
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
    )

    course: Mapped[Optional["Course"]] = relationship("Course")
    test: Mapped[Optional["Test"]] = relationship("Test")

    revoker: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[revoked_by],
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, native_enum=False, length=50),
        default=NotificationType.info,
    )

    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)

    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)

    dedupe_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    read_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["User"] = relationship("User")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(1024))
    action: Mapped[str] = mapped_column(String(100))

    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)

    status_code: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    user: Mapped[Optional["User"]] = relationship("User")