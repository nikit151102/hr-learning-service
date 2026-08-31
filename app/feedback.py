from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_current_user, get_or_404, paginate
from app.ext_models import MaterialFeedback
from app.ext_schemas import (
    FeedbackCreate,
    FeedbackRead,
    FeedbackUpdate,
    MaterialRatingRead,
)
from app.models import Material, User, UserRole
from app.schemas import Page


router = APIRouter(prefix="/materials", tags=["Отзывы"])


def _ensure_material_available(
    db: Session,
    material_id: UUID,
    current_user: User,
) -> Material:
    material = get_or_404(db, Material, material_id)

    if not material.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Материал не найден")

    return material


@router.post(
    "/{material_id}/feedback",
    response_model=FeedbackRead,
    summary="Оставить или обновить отзыв",
    description="Если отзыв уже есть, он будет обновлён.",
)
def upsert_feedback(
    material_id: UUID,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_material_available(db, material_id, current_user)

    existing = (
        db.query(MaterialFeedback)
        .filter(
            MaterialFeedback.material_id == material_id,
            MaterialFeedback.user_id == current_user.id,
        )
        .first()
    )

    if existing:
        existing.rating = payload.rating
        existing.comment = payload.comment
        feedback = existing
    else:
        feedback = MaterialFeedback(
            material_id=material_id,
            user_id=current_user.id,
            rating=payload.rating,
            comment=payload.comment,
        )
        db.add(feedback)

    db.commit()
    db.refresh(feedback)

    return feedback


@router.get(
    "/{material_id}/feedback",
    response_model=Page[FeedbackRead],
    summary="Отзывы о материале",
    description="Список отзывов о материале с пагинацией.",
)
def list_feedback(
    material_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_material_available(db, material_id, current_user)

    query = (
        db.query(MaterialFeedback)
        .filter(MaterialFeedback.material_id == material_id)
        .order_by(MaterialFeedback.created_at.desc())
    )

    return paginate(query, page, size)


@router.get(
    "/{material_id}/rating",
    response_model=MaterialRatingRead,
    summary="Рейтинг материала",
    description="Средний рейтинг и количество отзывов.",
)
def material_rating(
    material_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_material_available(db, material_id, current_user)

    avg_rating = (
        db.query(func.avg(MaterialFeedback.rating))
        .filter(MaterialFeedback.material_id == material_id)
        .scalar()
    )

    feedback_count = (
        db.query(func.count(MaterialFeedback.id))
        .filter(MaterialFeedback.material_id == material_id)
        .scalar()
        or 0
    )

    return {
        "material_id": material_id,
        "avg_rating": float(avg_rating) if avg_rating is not None else None,
        "feedback_count": int(feedback_count),
    }


@router.patch(
    "/{material_id}/feedback",
    response_model=FeedbackRead,
    summary="Изменить свой отзыв",
    description="Пользователь может изменить свой отзыв к материалу.",
)
def update_feedback(
    material_id: UUID,
    payload: FeedbackUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feedback = (
        db.query(MaterialFeedback)
        .filter(
            MaterialFeedback.material_id == material_id,
            MaterialFeedback.user_id == current_user.id,
        )
        .first()
    )

    if not feedback:
        raise HTTPException(status_code=404, detail="Отзыв не найден")

    data = payload.model_dump(exclude_unset=True)

    for key, value in data.items():
        setattr(feedback, key, value)

    db.commit()
    db.refresh(feedback)

    return feedback


@router.delete(
    "/{material_id}/feedback",
    status_code=204,
    summary="Удалить отзыв",
    description="Автор может удалить свой отзыв. HR/администратор может удалить любой отзыв.",
)
def delete_feedback(
    material_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feedback = (
        db.query(MaterialFeedback)
        .filter(MaterialFeedback.material_id == material_id)
        .first()
    )

    if not feedback:
        raise HTTPException(status_code=404, detail="Отзыв не найден")

    if feedback.user_id != current_user.id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    db.delete(feedback)
    db.commit()

    return None