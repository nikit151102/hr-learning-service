import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class InvitationStatus(str, enum.Enum):
    pending = "pending"        # Ожидает подтверждения админа
    approved = "approved"      # Подтверждено админом
    accepted = "accepted"      # Пользователь принял и создал аккаунт
    declined = "declined"      # Отклонено пользователем
    rejected = "rejected"      # Отклонено админом
    expired = "expired"        # Истекло
    canceled = "canceled"      # Отменено


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    email: Mapped[str] = mapped_column(String(255), index=True)
    id_max: Mapped[str] = mapped_column(String(255), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(512))

    invitation_code: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )

    status: Mapped[InvitationStatus] = mapped_column(
        SAEnum(InvitationStatus, native_enum=False, length=30),
        default=InvitationStatus.pending,
    )

    # Кто создал запрос (сам пользователь через бота)
    requested_by_id_max: Mapped[str] = mapped_column(String(255), nullable=True)

    # Кто подтвердил (админ/HR)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    role: Mapped[str] = mapped_column(String(50), default="employee")
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    approver = relationship("User", foreign_keys=[approved_by])

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)