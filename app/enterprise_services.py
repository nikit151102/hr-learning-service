from __future__ import annotations

import io
import os
import uuid
import datetime as dt
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, exists, func
from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.enterprise_models import (
    Certificate,
    Course,
    CourseEnrollment,
    CourseEnrollmentStatus,
    CourseItem,
    CourseItemProgress,
    EmployeeDepartment,
    ManagerRight,
    Notification,
    NotificationType,
)
from app.ext_models import Assignment, AssignmentStatus
from app.models import (
    AttemptStatus,
    Material,
    MaterialView,
    Test,
    TestAttempt,
    User,
    UserRole,
)
from app.services import minio_service


_FONT_NAME = "Helvetica"
_FONT_READY = False


def _register_fonts() -> str:
    global _FONT_NAME, _FONT_READY

    if _FONT_READY:
        return _FONT_NAME

    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans.ttf",
    ]

    for path in paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("DejaVuSans", path))
                _FONT_NAME = "DejaVuSans"
                break
            except Exception:
                pass

    _FONT_READY = True
    return _FONT_NAME


def generate_certificate_pdf(
    full_name: str,
    object_title: str,
    object_type: str,
    certificate_number: str,
    issued_at: datetime,
) -> bytes:
    font_name = _register_fonts()

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont(font_name, 30)
    c.drawCentredString(width / 2, height - 120, "СЕРТИФИКАТ")

    c.setFont(font_name, 18)
    c.drawCentredString(width / 2, height - 180, "Подтверждает, что")

    c.setFont(font_name, 22)
    c.drawCentredString(width / 2, height - 220, full_name)

    c.setFont(font_name, 18)
    c.drawCentredString(width / 2, height - 260, "успешно завершил(а)")

    c.setFont(font_name, 20)
    c.drawCentredString(width / 2, height - 300, object_title)

    c.setFont(font_name, 14)
    c.drawCentredString(width / 2, height - 340, f"Тип: {object_type}")
    c.drawCentredString(width / 2, height - 370, f"Номер сертификата: {certificate_number}")
    c.drawCentredString(
        width / 2,
        height - 395,
        f"Дата выдачи: {issued_at.strftime('%d.%m.%Y %H:%M')}",
    )

    c.showPage()
    c.save()

    return buffer.getvalue()


def _new_certificate_number() -> str:
    return f"CERT-{datetime.now().year}-{uuid.uuid4().hex[:10].upper()}"


def _upload_pdf(pdf_bytes: bytes) -> str:
    object_key = f"certificates/{dt.date.today():%Y/%m/%d}/{uuid.uuid4()}.pdf"

    minio_service.client.put_object(
        settings.minio_bucket,
        object_key,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )

    return object_key


def notify_user(
    db: Session,
    user_id: uuid.UUID,
    type_: NotificationType,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    if dedupe_key:
        exists_notification = (
            db.query(Notification)
            .filter(Notification.dedupe_key == dedupe_key)
            .first()
        )
        if exists_notification:
            return None

    notification = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        dedupe_key=dedupe_key,
        is_read=False,
    )

    db.add(notification)
    db.flush()

    return notification


def issue_test_certificate(
    db: Session,
    user_id: uuid.UUID,
    test_id: uuid.UUID,
) -> Certificate | None:
    user = db.get(User, user_id)
    test = db.get(Test, test_id)

    if not user or not test:
        return None

    existing = (
        db.query(Certificate)
        .filter(
            Certificate.user_id == user_id,
            Certificate.test_id == test_id,
            Certificate.revoked_at.is_(None),
        )
        .first()
    )

    if existing:
        return existing

    certificate_number = _new_certificate_number()
    issued_at = datetime.now(timezone.utc)

    pdf_bytes = generate_certificate_pdf(
        full_name=user.full_name,
        object_title=test.title,
        object_type="Тест",
        certificate_number=certificate_number,
        issued_at=issued_at,
    )

    object_key = _upload_pdf(pdf_bytes)

    certificate = Certificate(
        certificate_number=certificate_number,
        user_id=user_id,
        test_id=test_id,
        issued_at=issued_at,
        pdf_bucket=settings.minio_bucket,
        pdf_object_key=object_key,
    )

    db.add(certificate)
    db.flush()

    notify_user(
        db=db,
        user_id=user_id,
        type_=NotificationType.certificate_issued,
        title="Выдан сертификат",
        message=f"Вам выдан сертификат по тесту: {test.title}",
        entity_type="certificate",
        entity_id=certificate.id,
        dedupe_key=f"certificate_issued:{certificate.id}",
    )

    return certificate


def issue_course_certificate(
    db: Session,
    enrollment: CourseEnrollment,
) -> Certificate | None:
    course = enrollment.course
    user = enrollment.user

    if not course or not user:
        return None

    existing = (
        db.query(Certificate)
        .filter(
            Certificate.user_id == enrollment.user_id,
            Certificate.course_id == enrollment.course_id,
            Certificate.revoked_at.is_(None),
        )
        .first()
    )

    if existing:
        return existing

    certificate_number = _new_certificate_number()
    issued_at = datetime.now(timezone.utc)

    pdf_bytes = generate_certificate_pdf(
        full_name=user.full_name,
        object_title=course.title,
        object_type="Курс",
        certificate_number=certificate_number,
        issued_at=issued_at,
    )

    object_key = _upload_pdf(pdf_bytes)

    certificate = Certificate(
        certificate_number=certificate_number,
        user_id=enrollment.user_id,
        course_id=enrollment.course_id,
        issued_at=issued_at,
        pdf_bucket=settings.minio_bucket,
        pdf_object_key=object_key,
    )

    db.add(certificate)
    db.flush()

    notify_user(
        db=db,
        user_id=enrollment.user_id,
        type_=NotificationType.certificate_issued,
        title="Выдан сертификат",
        message=f"Вам выдан сертификат по курсу: {course.title}",
        entity_type="certificate",
        entity_id=certificate.id,
        dedupe_key=f"certificate_issued:{certificate.id}",
    )

    return certificate


def sync_missing_certificates(db: Session) -> None:
    passed_attempts = (
        db.query(TestAttempt)
        .filter(
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.passed.is_(True),
        )
        .all()
    )

    for attempt in passed_attempts:
        issue_test_certificate(db, attempt.user_id, attempt.test_id)

    completed_enrollments = (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.status == CourseEnrollmentStatus.completed)
        .all()
    )

    for enrollment in completed_enrollments:
        issue_course_certificate(db, enrollment)


# ==================== NOTIFICATION SCANS ====================

def create_assignment_notifications(db: Session) -> None:
    assignments = db.query(Assignment).all()

    for assignment in assignments:
        if assignment.material_id and assignment.material:
            object_title = assignment.material.title
            object_type = "материал"
        elif assignment.test_id and assignment.test:
            object_title = assignment.test.title
            object_type = "тест"
        else:
            object_title = "обучение"
            object_type = "объект"

        notify_user(
            db=db,
            user_id=assignment.user_id,
            type_=NotificationType.assignment_created,
            title="Новое назначение",
            message=f"Вам назначен {object_type}: {object_title}",
            entity_type="assignment",
            entity_id=assignment.id,
            dedupe_key=f"assignment_created:{assignment.id}",
        )


def create_course_enrollment_notifications(db: Session) -> None:
    enrollments = db.query(CourseEnrollment).all()

    for enrollment in enrollments:
        if not enrollment.course:
            continue

        notify_user(
            db=db,
            user_id=enrollment.user_id,
            type_=NotificationType.course_assigned,
            title="Назначен курс",
            message=f"Вам назначен курс: {enrollment.course.title}",
            entity_type="course_enrollment",
            entity_id=enrollment.id,
            dedupe_key=f"course_assigned:{enrollment.id}",
        )


def create_deadline_notifications(db: Session) -> None:
    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=3)

    assignments = (
        db.query(Assignment)
        .filter(
            Assignment.due_date.isnot(None),
            Assignment.due_date <= soon,
            Assignment.status.notin_(
                [AssignmentStatus.completed, AssignmentStatus.canceled]
            ),
        )
        .all()
    )

    for assignment in assignments:
        if assignment.due_date < now:
            type_ = NotificationType.overdue
            title = "Просроченное назначение"
            message = "У вас есть просроченное назначение."
            dedupe_key = f"assignment_overdue:{assignment.id}:{assignment.due_date.date()}"
        else:
            type_ = NotificationType.due_soon
            title = "Скоро дедлайн"
            message = "Приближается срок выполнения назначения."
            dedupe_key = f"assignment_due_soon:{assignment.id}:{assignment.due_date.date()}"

        notify_user(
            db=db,
            user_id=assignment.user_id,
            type_=type_,
            title=title,
            message=message,
            entity_type="assignment",
            entity_id=assignment.id,
            dedupe_key=dedupe_key,
        )

    enrollments = (
        db.query(CourseEnrollment)
        .filter(
            CourseEnrollment.due_date.isnot(None),
            CourseEnrollment.due_date <= soon,
            CourseEnrollment.status.notin_(
                [
                    CourseEnrollmentStatus.completed,
                    CourseEnrollmentStatus.canceled,
                ]
            ),
        )
        .all()
    )

    for enrollment in enrollments:
        if enrollment.due_date < now:
            type_ = NotificationType.overdue
            title = "Просроченный курс"
            message = "У вас есть просроченный курс."
            dedupe_key = f"course_overdue:{enrollment.id}:{enrollment.due_date.date()}"
        else:
            type_ = NotificationType.due_soon
            title = "Скоро дедлайн курса"
            message = "Приближается срок прохождения курса."
            dedupe_key = f"course_due_soon:{enrollment.id}:{enrollment.due_date.date()}"

        notify_user(
            db=db,
            user_id=enrollment.user_id,
            type_=type_,
            title=title,
            message=message,
            entity_type="course_enrollment",
            entity_id=enrollment.id,
            dedupe_key=dedupe_key,
        )


def create_attempt_result_notifications(db: Session) -> None:
    attempts = (
        db.query(TestAttempt)
        .filter(TestAttempt.status == AttemptStatus.completed)
        .all()
    )

    for attempt in attempts:
        test_title = attempt.test.title if attempt.test else "тест"

        if attempt.passed:
            type_ = NotificationType.test_passed
            title = "Тест пройден"
            message = f"Вы успешно прошли тест: {test_title}"
        else:
            type_ = NotificationType.test_failed
            title = "Тест не пройден"
            message = f"Тест не пройден: {test_title}"

        notify_user(
            db=db,
            user_id=attempt.user_id,
            type_=type_,
            title=title,
            message=message,
            entity_type="attempt",
            entity_id=attempt.id,
            dedupe_key=f"attempt_result:{attempt.id}",
        )


# ==================== COURSE PROGRESS ====================

def _is_course_item_completed(
    db: Session,
    item: CourseItem,
    user_id: uuid.UUID,
) -> bool:
    if item.material_id:
        viewed = (
            db.query(MaterialView)
            .filter(
                MaterialView.material_id == item.material_id,
                MaterialView.user_id == user_id,
            )
            .first()
        )
        return viewed is not None

    if item.test_id:
        passed_attempt = (
            db.query(TestAttempt)
            .filter(
                TestAttempt.test_id == item.test_id,
                TestAttempt.user_id == user_id,
                TestAttempt.status == AttemptStatus.completed,
                TestAttempt.passed.is_(True),
            )
            .first()
        )
        return passed_attempt is not None

    return False


def recalculate_enrollment(
    db: Session,
    enrollment: CourseEnrollment,
) -> CourseEnrollment:
    if enrollment.status == CourseEnrollmentStatus.canceled:
        return enrollment

    items = (
        db.query(CourseItem)
        .filter(CourseItem.course_id == enrollment.course_id)
        .order_by(CourseItem.sort_order)
        .all()
    )

    required_items = [item for item in items if item.is_required]

    denominator = len(required_items) if required_items else len(items)
    completed_required = 0
    completed_all = 0

    now = datetime.now(timezone.utc)

    progress_map = {progress.item_id: progress for progress in enrollment.progress}

    for item in items:
        completed = _is_course_item_completed(db, item, enrollment.user_id)

        progress = progress_map.get(item.id)

        if not progress:
            progress = CourseItemProgress(
                enrollment_id=enrollment.id,
                item_id=item.id,
                completed=False,
            )
            db.add(progress)
            progress_map[item.id] = progress

        if completed:
            completed_all += 1
            if item.is_required:
                completed_required += 1

            if not progress.completed:
                progress.completed = True
                progress.completed_at = now
        else:
            if progress.completed:
                progress.completed = False
                progress.completed_at = None

    completed_count = completed_required if required_items else completed_all

    enrollment.progress_percent = (
        int(round(completed_count * 100 / denominator)) if denominator else 0
    )

    if denominator and completed_count == denominator:
        if enrollment.status != CourseEnrollmentStatus.completed:
            enrollment.status = CourseEnrollmentStatus.completed
            enrollment.completed_at = now

            issue_course_certificate(db, enrollment)

            notify_user(
                db=db,
                user_id=enrollment.user_id,
                type_=NotificationType.course_completed,
                title="Курс завершён",
                message=f"Вы завершили курс: {enrollment.course.title if enrollment.course else ''}",
                entity_type="course_enrollment",
                entity_id=enrollment.id,
                dedupe_key=f"course_completed:{enrollment.id}",
            )
    else:
        if enrollment.status == CourseEnrollmentStatus.assigned and completed_count > 0:
            enrollment.status = CourseEnrollmentStatus.in_progress

    return enrollment


# ==================== MANAGEMENT ACCESS ====================

def get_manager_department(
    db: Session,
    current_user: User,
    requested_department: str | None = None,
) -> str | None:
    if current_user.role in (UserRole.admin, UserRole.hr):
        return requested_department

    manager_right = (
        db.query(ManagerRight)
        .filter(ManagerRight.user_id == current_user.id)
        .first()
    )

    if not manager_right:
        raise HTTPException(status_code=403, detail="Нет прав руководителя")

    if manager_right.department:
        return manager_right.department

    return requested_department


def get_employee_department(db: Session, user_id: uuid.UUID) -> str | None:
    row = (
        db.query(EmployeeDepartment)
        .filter(EmployeeDepartment.user_id == user_id)
        .first()
    )
    return row.department if row else None