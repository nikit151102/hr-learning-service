import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.invitation_models import Invitation, InvitationStatus
from app.models import User, UserRole, LocationType
from uuid import UUID
from app.models import Location, User

def generate_invitation_code() -> str:
    return secrets.token_urlsafe(32)


def request_invitation(
    db: Session,
    email: str,
    full_name: str,
    id_max: str,
    requested_by_id_max: str,
    location_id: Optional[UUID] = None, 
    role: str = "employee",
    department: Optional[str] = None,
    expires_in_days: int = 7,
) -> Invitation:
    """Пользователь запрашивает приглашение через бота"""

    # Проверяем, нет ли активного запроса
    existing = (
        db.query(Invitation)
        .filter(
            Invitation.requested_by_id_max == requested_by_id_max,
            Invitation.status.in_([
                InvitationStatus.pending,
            ]),
        )
        .first()
    )

    if existing and not existing.is_expired():
        raise HTTPException(
            status_code=409,
            detail=f"У вас уже есть активное приглашение (статус: {existing.status.value})",
        )

    # Проверяем, не зарегистрирован ли уже пользователь
    existing_user = db.query(User).filter(User.id_max == id_max).first()
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail=f"Пользователь с id_max={id_max} уже зарегистрирован",
        )

    invitation_code = generate_invitation_code()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    if location_id:
        location = db.query(Location).filter(
            Location.id == location_id,
            Location.is_active.is_(True)
        ).first()
        if not location:
            raise HTTPException(status_code=404, detail="Подразделение не найдено")

    invitation = Invitation(
        email=email,
        id_max=id_max,
        full_name=full_name,
        invitation_code=generate_invitation_code(),
        status=InvitationStatus.pending,
        requested_by_id_max=requested_by_id_max,
        location_id=location_id,  # ← сохраняем
        role=role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def approve_invitation(
    db: Session,
    invitation_id: UUID,
    approved_by: UUID,
    role: str = "employee",
    department: str | None = None,
) -> Invitation:
    invitation = get_or_404(db, Invitation, invitation_id)

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(status_code=409, detail="Invitation is not pending")

    if invitation.is_expired():
        invitation.status = InvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=410, detail="Invitation has expired")

    # === СОЗДАЁМ ПОЛЬЗОВАТЕЛЯ С location_id ===
    user = User(
        id_max=invitation.id_max,
        full_name=invitation.full_name,
        role=UserRole(role),
        is_active=True,
        location_id=invitation.location_id,  # ← КОПИРУЕМ location_id
    )

    db.add(user)

    invitation.status = InvitationStatus.accepted
    invitation.approved_by = approved_by
    invitation.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(invitation)

    return invitation
    

def reject_invitation(
    db: Session,
    invitation_id: uuid.UUID,
    reason: Optional[str] = None,
) -> Invitation:
    """Админ отклоняет приглашение"""

    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя отклонить приглашение со статусом {invitation.status.value}",
        )

    invitation.status = InvitationStatus.rejected
    invitation.rejected_at = datetime.now(timezone.utc)
    invitation.reject_reason = reason

    db.commit()
    db.refresh(invitation)

    return invitation


def get_invitation_by_id_max(
    db: Session,
    id_max: str,
) -> Optional[Invitation]:
    """Получает последнее приглашение для пользователя"""
    return (
        db.query(Invitation)
        .filter(Invitation.requested_by_id_max == id_max)
        .order_by(Invitation.created_at.desc())
        .first()
    )


def list_invitations(
    db: Session,
    status: Optional[InvitationStatus] = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """Возвращает приглашения с информацией о подразделении"""

    query = db.query(Invitation)

    if status:
        query = query.filter(Invitation.status == status)

    total = query.count()

    items = (
        query
        .outerjoin(Location, Invitation.location_id == Location.id)
        .order_by(Invitation.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    # Обогащаем каждый объект информацией о подразделении
    enriched = []
    for inv in items:
        inv_dict = {
            "id": inv.id,
            "email": inv.email,
            "id_max": inv.id_max,
            "full_name": inv.full_name,
            "invitation_code": inv.invitation_code,
            "status": inv.status,
            "requested_by_id_max": inv.requested_by_id_max,
            "approved_by": inv.approved_by,
            "role": inv.role,
            "department": inv.department,
            "expires_at": inv.expires_at,
            "approved_at": inv.approved_at,
            "accepted_at": inv.accepted_at,
            "rejected_at": inv.rejected_at,
            "reject_reason": inv.reject_reason,
            "created_at": inv.created_at,
            "updated_at": inv.updated_at,
            "location_id": inv.location_id,
            "location_name": inv.location.name if inv.location else None,
            "location_address": inv.location.address if inv.location else None,
            "location_city": inv.location.city if inv.location else None,
            "location_type": inv.location.location_type.value if inv.location else None,
        }
        enriched.append(inv_dict)

    return enriched, total