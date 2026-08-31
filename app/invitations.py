from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_current_user
from app.invitation_models import InvitationStatus
from app.invitation_schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationDecline,
    InvitationRead,
    InvitationResponse,
)
from app.services.invitation_service import (
    accept_invitation,
    cancel_invitation,
    create_invitation,
    decline_invitation,
    list_invitations,
)
from app.models import User
from app.schemas import Page

router = APIRouter(prefix="/invitations", tags=["Приглашения"])


@router.post(
    "",
    response_model=InvitationRead,
    status_code=201,
    summary="Создать приглашение",
    description="Создаёт новое приглашение для пользователя",
)
def create_invitation_endpoint(
    payload: InvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    invitation = create_invitation(
        db=db,
        email=payload.email,
        full_name=payload.full_name,
        invited_by=current_user.id,
        id_max=payload.id_max,
        role=payload.role,
        department=payload.department,
        expires_in_days=payload.expires_in_days,
    )

    # Здесь можно добавить отправку email/уведомления
    # send_invitation_email(invitation)

    return invitation


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
    from app.invitation_models import Invitation

    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    return invitation


@router.post(
    "/{invitation_id}/cancel",
    response_model=InvitationRead,
    summary="Отменить приглашение",
    description="Отменяет активное приглашение",
)
def cancel_invitation_endpoint(
    invitation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return cancel_invitation(db, invitation_id)


@router.post(
    "/accept",
    response_model=InvitationResponse,
    summary="Принять приглашение",
    description="Принимает приглашение и создаёт пользователя",
)
def accept_invitation_endpoint(
    payload: InvitationAccept,
    db: Session = Depends(get_db),
):
    user = accept_invitation(db, payload.invitation_code, payload.password)

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


@router.post(
    "/decline",
    response_model=InvitationResponse,
    summary="Отклонить приглашение",
    description="Отклоняет приглашение",
)
def decline_invitation_endpoint(
    payload: InvitationDecline,
    db: Session = Depends(get_db),
):
    invitation = decline_invitation(db, payload.invitation_code, payload.reason)

    return InvitationResponse(
        success=True,
        message="Приглашение отклонено",
        invitation=InvitationRead.model_validate(invitation),
    )


@router.get(
    "/check/{code}",
    response_model=InvitationRead,
    summary="Проверить приглашение",
    description="Проверяет действительность приглашения по коду",
)
def check_invitation_endpoint(
    code: str,
    db: Session = Depends(get_db),
):
    from app.invitation_models import Invitation

    invitation = db.query(Invitation).filter(Invitation.invitation_code == code).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invitation.is_expired():
        raise HTTPException(status_code=410, detail="Приглашение истекло")

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Приглашение уже {invitation.status.value}",
        )

    return invitation