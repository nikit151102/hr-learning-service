from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired
from app.invitation_models import Invitation, InvitationStatus
from app.invitation_schemas import (
    InvitationApprove,
    InvitationRead,
    InvitationReject,
    InvitationRequest,
)
from app.services.invitation_service import (
    approve_invitation,
    get_invitation_by_id_max,
    reject_invitation,
    request_invitation,
    list_invitations,
)
from app.models import User
from app.schemas import Page

router = APIRouter(prefix="/invitations", tags=["Приглашения"])


@router.post(
    "/request",
    response_model=InvitationRead,
    status_code=201,
    summary="Запросить приглашение",
)
def request_invitation_endpoint(
    payload: InvitationRequest,
    db: Session = Depends(get_db),
):
    """Публичный endpoint - пользователь сам запрашивает приглашение"""
    return request_invitation(
        db=db,
        email=payload.email,
        full_name=payload.full_name,
        id_max=payload.id_max,
        requested_by_id_max=payload.id_max,
        role=payload.role,
        department=payload.department,
        expires_in_days=payload.expires_in_days,
    )


@router.get(
    "/my",
    response_model=Optional[InvitationRead],
    summary="Моё приглашение",
)
def get_my_invitation_endpoint(
    id_max: str = Query(..., description="ID Max пользователя"),
    db: Session = Depends(get_db),
):
    """Публичный endpoint - проверка статуса своего приглашения"""
    invitation = get_invitation_by_id_max(db, id_max)
    return invitation


@router.get(
    "",
    response_model=Page[InvitationRead],
    summary="Список приглашений",
)
def list_invitations_endpoint(
    status: Optional[InvitationStatus] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    invitations, total = list_invitations(db, status, page, size)
    return {
        "items": invitations,
        "total": total,
        "page": page,
        "size": size,
    }


@router.get(
    "/{invitation_id}",
    response_model=InvitationRead,
    summary="Получить приглашение",
)
def get_invitation_endpoint(
    invitation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    return invitation


@router.post(
    "/{invitation_id}/approve",
    response_model=InvitationRead,
    summary="Подтвердить приглашение",
    description="При подтверждении СРАЗУ создаётся пользователь",
)
def approve_invitation_endpoint(
    invitation_id: UUID,
    payload: InvitationApprove,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return approve_invitation(
        db=db,
        invitation_id=invitation_id,
        approved_by=current_user.id,
        role=payload.role,
        department=payload.department,
    )


@router.post(
    "/{invitation_id}/reject",
    response_model=InvitationRead,
    summary="Отклонить приглашение",
)
def reject_invitation_endpoint(
    invitation_id: UUID,
    payload: InvitationReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return reject_invitation(db, invitation_id, payload.reason)