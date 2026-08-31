from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.invitation_models import InvitationStatus


class InvitationRequest(BaseModel):
    """Запрос приглашения от пользователя"""
    email: EmailStr = Field(description="Email пользователя")
    id_max: str = Field(description="Корпоративный идентификатор из MAX")
    full_name: str = Field(description="ФИО пользователя")
    role: str = Field(default="employee", description="Запрашиваемая роль")
    department: Optional[str] = Field(
        default=None, description="Отдел (опционально)"
    )
    expires_in_days: int = Field(
        default=7, ge=1, le=30, description="Срок действия приглашения в днях"
    )


class InvitationApprove(BaseModel):
    """Подтверждение приглашения админом"""
    role: Optional[str] = Field(
        default=None, description="Назначить роль (опционально)"
    )
    department: Optional[str] = Field(
        default=None, description="Назначить отдел (опционально)"
    )


class InvitationReject(BaseModel):
    """Отклонение приглашения админом"""
    reason: Optional[str] = Field(
        default=None, description="Причина отклонения (опционально)"
    )


class InvitationCreate(BaseModel):
    """Создание приглашения админом (старый вариант)"""
    email: EmailStr = Field(description="Email приглашаемого пользователя")
    id_max: Optional[str] = Field(
        default=None,
        description="Корпоративный идентификатор (если известен)",
    )
    full_name: str = Field(description="ФИО приглашаемого")
    role: str = Field(default="employee", description="Роль пользователя")
    department: Optional[str] = Field(
        default=None, description="Отдел (опционально)"
    )
    expires_in_days: int = Field(
        default=7, ge=1, le=30, description="Срок действия приглашения в днях"
    )


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    id_max: Optional[str]
    full_name: str
    invitation_code: str
    status: InvitationStatus
    requested_by_id_max: Optional[str]
    invited_by: Optional[UUID]
    approved_by: Optional[UUID]
    role: str
    department: Optional[str]
    expires_at: datetime
    approved_at: Optional[datetime]
    accepted_at: Optional[datetime]
    declined_at: Optional[datetime]
    rejected_at: Optional[datetime]
    reject_reason: Optional[str]
    decline_reason: Optional[str]
    created_at: datetime


class InvitationAccept(BaseModel):
    invitation_code: str = Field(description="Код приглашения")
    id_max: str = Field(description="ID Max пользователя")


class InvitationDecline(BaseModel):
    invitation_code: str = Field(description="Код приглашения")
    reason: Optional[str] = Field(
        default=None, description="Причина отказа (опционально)"
    )


class InvitationResponse(BaseModel):
    success: bool
    message: str
    invitation: Optional[InvitationRead] = None
    user_id: Optional[UUID] = None