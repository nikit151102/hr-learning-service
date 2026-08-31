from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.enterprise_services import (
    create_assignment_notifications,
    create_attempt_result_notifications,
    create_course_enrollment_notifications,
    create_deadline_notifications,
    sync_missing_certificates,
)


scheduler = AsyncIOScheduler(timezone="UTC")


def notification_scan(db: Session) -> None:
    create_assignment_notifications(db)
    create_course_enrollment_notifications(db)
    create_deadline_notifications(db)
    create_attempt_result_notifications(db)


def certificate_scan(db: Session) -> None:
    sync_missing_certificates(db)


def _wrap_job(func):
    def wrapper():
        db = SessionLocal()
        try:
            func(db)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    return wrapper


def setup_scheduler() -> None:
    scheduler.add_job(
        _wrap_job(notification_scan),
        trigger="interval",
        minutes=15,
        id="notification_scan",
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _wrap_job(certificate_scan),
        trigger="interval",
        minutes=30,
        id="certificate_scan",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)