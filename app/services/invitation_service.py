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


def create_invitation(
    db: Session,
    email: str,
    full_name: str,
    invited_by: uuid.UUID,
    id_max: Optional[str] = None,
    role: str = "employee",
    department: Optional[str] = None,
    expires_in_days: int = 7,
) -> Invitation:
    """Создаёт новое приглашение"""

    # Проверяем, нет ли уже активного приглашения для этого email
    existing = (
        db.query(Invitation)
        .filter(
            Invitation.email == email,
            Invitation.status == InvitationStatus.pending,
        )
        .first()
    )

    if existing and not existing.is_expired():
        raise HTTPException(
            status_code=409,
            detail=f"Активное приглашение для {email} уже существует",
        )

    # Проверяем, нет ли уже пользователя с таким email
    existing_user = db.query(User).filter(User.id_max == id_max).first() if id_max else None

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
        invited_by=invited_by,
        role=role,
        department=department,
        expires_at=expires_at,
    )

    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    return invitation


def get_invitation_by_code(db: Session, code: str) -> Optional[Invitation]:
    """Получает приглашение по коду"""
    return (
        db.query(Invitation)
        .filter(Invitation.invitation_code == code)
        .first()
    )


def accept_invitation(
    db: Session,
    code: str,
    id_max: Optional[str] = None,
) -> User:
    """Принимает приглашение и создаёт пользователя"""

    invitation = get_invitation_by_code(db, code)

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Приглашение уже {invitation.status.value}",
        )

    if invitation.is_expired():
        invitation.status = InvitationStatus.expired
        db.commit()
        raise HTTPException(status_code=410, detail="Приглашение истекло")

    # Проверяем, не занят ли id_max
    final_id_max = id_max or invitation.id_max

    if not final_id_max:
        raise HTTPException(
            status_code=422,
            detail="Необходимо указать id_max для регистрации",
        )

    existing_user = db.query(User).filter(User.id_max == final_id_max).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail=f"Пользователь с id_max={final_id_max} уже существует",
        )

    # Создаём пользователя
    user = User(
        id_max=final_id_max,
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


def decline_invitation(
    db: Session,
    code: str,
    reason: Optional[str] = None,
) -> Invitation:
    """Отклоняет приглашение"""

    invitation = get_invitation_by_code(db, code)

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Приглашение уже {invitation.status.value}",
        )

    invitation.status = InvitationStatus.declined
    invitation.declined_at = datetime.now(timezone.utc)
    invitation.decline_reason = reason

    db.commit()
    db.refresh(invitation)

    return invitation


def cancel_invitation(db: Session, invitation_id: uuid.UUID) -> Invitation:
    """Отменяет приглашение (администратором)"""

    invitation = db.query(Invitation).filter(Invitation.id == invitation_id).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")

    if invitation.status != InvitationStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя отменить приглашение со статусом {invitation.status.value}",
        )

    invitation.status = InvitationStatus.canceled
    db.commit()
    db.refresh(invitation)

    return invitation


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