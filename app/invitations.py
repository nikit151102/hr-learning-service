from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_current_user
from app.invitation_models import Invitation, InvitationStatus
from app.invitation_schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationDecline,
    InvitationRead,
    InvitationResponse,
    InvitationRequest,
    InvitationApprove,
    InvitationReject,
)
from app.services.invitation_service import (
    accept_approved_invitation,
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
    description="Пользователь запрашивает приглашение через бота",
)
def request_invitation_endpoint(
    payload: InvitationRequest,
    db: Session = Depends(get_db),
):
    """Публичный endpoint - пользователь сам запрашивает приглашение"""
    invitation = request_invitation(
        db=db,
        email=payload.email,
        full_name=payload.full_name,
        id_max=payload.id_max,
        requested_by_id_max=payload.id_max,
        role=payload.role,
        department=payload.department,
        expires_in_days=payload.expires_in_days,
    )

    return invitation


@router.get(
    "/my",
    response_model=Optional[InvitationRead],
    summary="Моё приглашение",
    description="Получить последнее приглашение для текущего пользователя",
)
def get_my_invitation_endpoint(
    id_max: str = Query(..., description="ID Max пользователя"),
    db: Session = Depends(get_db),
):
    """Публичный endpoint - проверка статуса своего приглашения"""
    invitation = get_invitation_by_id_max(db, id_max)
    
    if not invitation:
        return None
    
    return invitation


@router.post(
    "/{invitation_id}/approve",
    response_model=InvitationRead,
    summary="Подтвердить приглашение",
    description="Админ подтверждает приглашение",
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
    description="Админ отклоняет приглашение",
)
def reject_invitation_endpoint(
    invitation_id: UUID,
    payload: InvitationReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return reject_invitation(db, invitation_id, payload.reason)


@router.get(
    "",
    response_model=Page[InvitationRead],
    summary="Список приглашений",
    description="Возвращает список приглашений с фильтрацией по статусу",
)
def list_invitations_endpoint(
    status: Optional[InvitationStatus] = Query(
        default=None, description="Фильтр по статусу"
    ),
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
    description="Возвращает детальную информацию о приглашении",
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
    "/accept",
    response_model=InvitationResponse,
    summary="Принять приглашение",
    description="Принимает подтверждённое приглашение и создаёт пользователя",
)
def accept_invitation_endpoint(
    payload: InvitationAccept,
    db: Session = Depends(get_db),
):
    """Публичный endpoint - пользователь принимает подтверждённое приглашение"""
    user = accept_approved_invitation(db, payload.invitation_code, payload.id_max)

    invitation = (
        db.query(Invitation)
        .filter(Invitation.invitation_code == payload.invitation_code)
        .first()
    )

    return InvitationResponse(
        success=True,
        message="Приглашение принято, пользователь создан",
        invitation=InvitationRead.model_validate(invitation),
        user_id=user.id,
    )