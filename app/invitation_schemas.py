from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.invitation_models import InvitationStatus


class InvitationRequest(BaseModel):
    email: EmailStr
    id_max: str
    full_name: str
    role: str = "employee"
    department: Optional[str] = None
    expires_in_days: int = Field(default=7, ge=1, le=30)


class InvitationApprove(BaseModel):
    role: Optional[str] = None
    department: Optional[str] = None


class InvitationReject(BaseModel):
    reason: Optional[str] = None


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    id_max: Optional[str]
    full_name: str
    invitation_code: str
    status: InvitationStatus
    requested_by_id_max: Optional[str]
    approved_by: Optional[UUID]
    role: str
    department: Optional[str]
    expires_at: datetime
    approved_at: Optional[datetime]
    accepted_at: Optional[datetime]
    rejected_at: Optional[datetime]
    reject_reason: Optional[str]
    created_at: datetime