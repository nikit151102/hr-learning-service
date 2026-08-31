from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.invitation_models import InvitationStatus


class InvitationCreate(BaseModel):
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
    invited_by: Optional[UUID]
    role: str
    department: Optional[str]
    expires_at: datetime
    accepted_at: Optional[datetime]
    declined_at: Optional[datetime]
    decline_reason: Optional[str]
    created_at: datetime


class InvitationAccept(BaseModel):
    invitation_code: str = Field(description="Код приглашения")
    password: Optional[str] = Field(
        default=None,
        description="Пароль (если требуется)",
    )


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