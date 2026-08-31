from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_current_user, get_or_404, paginate
from app.enterprise_models import Notification
from app.enterprise_schemas import NotificationRead, UnreadNotificationsCount
from app.enterprise_services import (
    create_assignment_notifications,
    create_attempt_result_notifications,
    create_course_enrollment_notifications,
    create_deadline_notifications,
)
from app.models import User
from app.schemas import Page


router = APIRouter(prefix="/notifications", tags=["Уведомления"])


@router.get(
    "/me",
    response_model=Page[NotificationRead],
    summary="Мои уведомления",
    description="Список уведомлений текущего пользователя.",
)
def my_notifications(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
    )

    return paginate(query, page, size)


@router.get(
    "/me/unread-count",
    response_model=UnreadNotificationsCount,
    summary="Количество непрочитанных",
    description="Количество непрочитанных уведомлений.",
)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .scalar()
        or 0
    )

    return {"unread": int(count)}


@router.post(
    "/jobs/scan",
    summary="Запустить генерацию уведомлений",
    description="Служебный эндпоинт для ручной генерации уведомлений.",
)
def notification_scan_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    create_assignment_notifications(db)
    create_course_enrollment_notifications(db)
    create_deadline_notifications(db)
    create_attempt_result_notifications(db)

    db.commit()

    return {"ok": True}


@router.post(
    "/read-all",
    summary="Прочитать все",
    description="Отмечает все уведомления пользователя как прочитанные.",
)
def read_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone

    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ).update(
        {
            Notification.is_read: True,
            Notification.read_at: datetime.now(timezone.utc),
        },
        synchronize_session=False,
    )

    db.commit()

    return {"ok": True}


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Прочитать уведомление",
    description="Отмечает одно уведомление как прочитанное.",
)
def read_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = get_or_404(db, Notification, notification_id)

    if notification.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if not notification.is_read:
        from datetime import datetime, timezone

        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(notification)

    return notification