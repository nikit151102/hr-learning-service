from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.ext_models import Assignment, AssignmentStatus, MaterialFeedback
from app.ext_schemas import MyDashboard
from app.models import AttemptStatus, MaterialView, TestAttempt, User


router = APIRouter(prefix="/me", tags=["Текущий пользователь"])


@router.get(
    "/dashboard",
    response_model=MyDashboard,
    summary="Моя сводка",
    description="Личная статистика текущего пользователя: попытки, просмотры, назначения и отзывы.",
)
def my_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)

    completed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.user_id == current_user.id,
            TestAttempt.status == AttemptStatus.completed,
        )
        .scalar()
        or 0
    )

    passed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.user_id == current_user.id,
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.passed.is_(True),
        )
        .scalar()
        or 0
    )

    avg_score = (
        db.query(func.avg(TestAttempt.score))
        .filter(
            TestAttempt.user_id == current_user.id,
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.score.isnot(None),
        )
        .scalar()
    )

    views_total = (
        db.query(func.count(MaterialView.id))
        .filter(MaterialView.user_id == current_user.id)
        .scalar()
        or 0
    )

    assignments_total = (
        db.query(func.count(Assignment.id))
        .filter(Assignment.user_id == current_user.id)
        .scalar()
        or 0
    )

    assignments_completed = (
        db.query(func.count(Assignment.id))
        .filter(
            Assignment.user_id == current_user.id,
            Assignment.status == AssignmentStatus.completed,
        )
        .scalar()
        or 0
    )

    assignments_in_progress = (
        db.query(func.count(Assignment.id))
        .filter(
            Assignment.user_id == current_user.id,
            Assignment.status == AssignmentStatus.in_progress,
        )
        .scalar()
        or 0
    )

    assignments_overdue = (
        db.query(func.count(Assignment.id))
        .filter(
            Assignment.user_id == current_user.id,
            Assignment.status.notin_(
                [AssignmentStatus.completed, AssignmentStatus.canceled]
            ),
            Assignment.due_date.isnot(None),
            Assignment.due_date < now,
        )
        .scalar()
        or 0
    )

    feedback_count = (
        db.query(func.count(MaterialFeedback.id))
        .filter(MaterialFeedback.user_id == current_user.id)
        .scalar()
        or 0
    )

    return {
        "completed_attempts": completed_attempts,
        "passed_attempts": passed_attempts,
        "failed_attempts": completed_attempts - passed_attempts,
        "avg_score": float(avg_score) if avg_score is not None else None,
        "views_total": int(views_total),
        "assignments_total": assignments_total,
        "assignments_completed": assignments_completed,
        "assignments_in_progress": assignments_in_progress,
        "assignments_overdue": assignments_overdue,
        "feedback_count": feedback_count,
    }