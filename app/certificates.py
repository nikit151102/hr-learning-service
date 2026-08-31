from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.deps import AdminRequired, HRRequired, get_current_user, get_or_404
from app.enterprise_models import Certificate
from app.enterprise_schemas import CertificateRead, CertificateVerify
from app.enterprise_services import sync_missing_certificates
from app.models import Test, User, UserRole
from app.enterprise_models import Course
from app.schemas import Page
from app.services import minio_service


router = APIRouter(prefix="/certificates", tags=["Сертификаты"])


@router.get(
    "/my",
    response_model=Page[CertificateRead],
    summary="Мои сертификаты",
    description="Список сертификатов текущего пользователя.",
)
def my_certificates(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Certificate)
        .filter(Certificate.user_id == current_user.id)
        .order_by(Certificate.issued_at.desc())
    )

    return paginate(query, page, size)


@router.post(
    "/sync",
    summary="Синхронизировать сертификаты",
    description="Выдаёт недостающие сертификаты за пройденные тесты и завершённые курсы.",
)
def sync_certificates(
    db: Session = Depends(get_db),
    current_user: User = Depends(AdminRequired),
):
    sync_missing_certificates(db)
    db.commit()

    return {"ok": True}


@router.get(
    "/verify/{certificate_number}",
    response_model=CertificateVerify,
    summary="Проверка сертификата",
    description="Публичная проверка сертификата по номеру.",
)
def verify_certificate(
    certificate_number: str,
    db: Session = Depends(get_db),
):
    certificate = (
        db.query(Certificate)
        .filter(Certificate.certificate_number == certificate_number)
        .first()
    )

    if not certificate:
        raise HTTPException(status_code=404, detail="Сертификат не найден")

    user = certificate.user

    if certificate.course_id:
        object_type = "course"
        course = db.get(Course, certificate.course_id)
        object_title = course.title if course else ""
    else:
        object_type = "test"
        test = db.get(Test, certificate.test_id)
        object_title = test.title if test else ""

    return {
        "valid": certificate.revoked_at is None,
        "certificate_number": certificate.certificate_number,
        "issued_at": certificate.issued_at,
        "revoked_at": certificate.revoked_at,
        "owner_full_name": user.full_name if user else "",
        "object_type": object_type,
        "object_title": object_title,
    }


@router.get(
    "/{certificate_id}/download",
    summary="Скачать сертификат",
    description="Скачивание PDF-сертификата владельцем или HR/администратором.",
)
def download_certificate(
    certificate_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    certificate = get_or_404(db, Certificate, certificate_id)

    if current_user.id != certificate.user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    url = minio_service.presigned_url(certificate.pdf_object_key)
    return RedirectResponse(url)


@router.post(
    "/{certificate_id}/revoke",
    response_model=CertificateRead,
    summary="Отозвать сертификат",
    description="Отзыв сертификата администратором/HR.",
)
def revoke_certificate(
    certificate_id: UUID,
    reason: str | None = Query(default=None, description="Причина отзыва"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    certificate = get_or_404(db, Certificate, certificate_id)

    if certificate.revoked_at:
        raise HTTPException(status_code=409, detail="Сертификат уже отозван")

    from datetime import datetime, timezone

    certificate.revoked_at = datetime.now(timezone.utc)
    certificate.revoked_by = current_user.id
    certificate.revoke_reason = reason

    db.commit()
    db.refresh(certificate)

    return certificate