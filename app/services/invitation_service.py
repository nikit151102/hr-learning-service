import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.invitation_models import Invitation, InvitationStatus
from app.models import User, UserRole


def generate_invitation_code() -> str:
    """Генерирует уникальный код приглашения"""
    return secrets.token_urlsafe(32)


def request_invitation(
    db: Session,
    email: str,
    full_name: str,
    id_max: str,
    requested_by_id_max: str,
    role: str = "employee",
    department: Optional[str] = None,
    expires_in_days: int = 7,
) -> Invitation:
    """Пользователь запрашивает приглашение через бота"""

    # Проверяем, нет ли уже активного запроса для этого id_max
    existing = (
        db.query(Invitation)
        .filter(
            Invitation.requested_by_id_max == requested_by_id_max,
            Invitation.status.in_([
                InvitationStatus.pending,
                InvitationStatus.approved,
            ]),
        )
        .first()
    )

    if existing and not existing.is_expired():
        raise HTTPException(
            status_code=409,
            detail=f"У вас уже есть активное приглашение (статус: {existing.status.value})",
        )

    # Проверяем, нет ли уже пользователя с таким id_max
    existing_user = db.query(User).filter(User.id_max == id_max).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail=f"Пользователь с id_max={id_max} уже зарегистрирован",
        )

    invitation_code = generate_invitation_code()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    invitation = Invitation(
        email=email,
        id_max=id_max,
        full_name=full_name,
        invitation_code=invitation_code,
        status=InvitationStatus.pending,
        requested_by_id_max=requested_by_id_max,
        role=role,
        department=department,
        expires_at=expires_at,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    return invitation


def approve_invitation(
    db: Session,
    invitation_id: uuid.UUID,
    approved_by: uuid.UUID,
    role: Optional[str] = None,
    department: Optional[str] = None,
) -> Invitation:
    """Админ подтверждает приглашение"""

    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя подтвердить приглашение со статусом {invitation.status.value}",
        )

    if invitation.is_expired():
        invitation.status = InvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=410, detail="Приглашение истекло")

    invitation.status = InvitationStatus.approved
    invitation.approved_by = approved_by
    invitation.approved_at = datetime.now(timezone.utc)

    if role:
        invitation.role = role
    if department:
        invitation.department = department

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


def accept_approved_invitation(
    db: Session,
    code: str,
    id_max: str,
) -> User:
    """Пользователь принимает подтверждённое приглашение"""

    invitation = (
        db.query(Invitation)
        .filter(Invitation.invitation_code == code)
        .first()
    )

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invitation.status != InvitationStatus.approved:
        raise HTTPException(
            status_code=409,
            detail=f"Приглашение должно быть подтверждено администратором (текущий статус: {invitation.status.value})",
        )

    if invitation.is_expired():
        invitation.status = InvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=410, detail="Приглашение истекло")

    # Проверяем соответствие id_max
    if invitation.id_max != id_max:
        raise HTTPException(
            status_code=403,
            detail="Приглашение не принадлежит этому пользователю",
        )

    # Проверяем, не создан ли уже пользователь
    existing_user = db.query(User).filter(User.id_max == id_max).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail=f"Пользователь с id_max={id_max} уже существует",
        )

    # Создаём пользователя
    user = User(
        id_max=id_max,
        full_name=invitation.full_name,
        role=UserRole(invitation.role),
        is_active=True,
    )

    db.add(user)

    # Обновляем приглашение
    invitation.status = InvitationStatus.accepted
    invitation.accepted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)

    return user


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
) -> tuple[list[Invitation], int]:
    """Возвращает список приглашений с пагинацией"""

    query = db.query(Invitation)

    if status:
        query = query.filter(Invitation.status == status)

    total = query.count()

    invitations = (
        query.order_by(Invitation.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return invitations, total