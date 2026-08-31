from __future__ import annotations

import enum
import uuid
import datetime as dt
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class AssignmentStatus(str, enum.Enum):
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    canceled = "canceled"


class Assignment(Base):
    __tablename__ = "assignments"

    __table_args__ = (
        CheckConstraint(
            """
            (material_id IS NOT NULL AND test_id IS NULL)
            OR
            (material_id IS NULL AND test_id IS NOT NULL)
            """,
            name="ck_assignment_object",
        ),
        Index("ix_assignments_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
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

    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(AssignmentStatus, native_enum=False, length=30),
        default=AssignmentStatus.assigned,
    )

    due_date: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

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

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
    )
    assigned_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[assigned_by],
    )
    material: Mapped[Optional["Material"]] = relationship("Material")
    test: Mapped[Optional["Test"]] = relationship("Test")


class MaterialFeedback(Base):
    __tablename__ = "material_feedback"

    __table_args__ = (
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_material_feedback_rating",
        ),
        UniqueConstraint(
            "material_id",
            "user_id",
            name="uq_material_feedback_user",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    material_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    material: Mapped["Material"] = relationship("Material")
    user: Mapped["User"] = relationship("User")