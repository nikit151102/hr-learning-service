from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_current_user, get_or_404, paginate
from app.ext_models import Assignment, AssignmentStatus
from app.ext_schemas import (
    AssignmentBulkCreate,
    AssignmentBulkResult,
    AssignmentCreate,
    AssignmentRead,
    AssignmentUpdate,
)
from app.models import (
    AttemptStatus,
    Material,
    MaterialView,
    Test,
    TestAttempt,
    User,
    UserRole,
)
from app.schemas import Page


router = APIRouter(prefix="/assignments", tags=["Назначения"])


@router.get(
    "/me",
    response_model=Page[AssignmentRead],
    summary="Мои назначения",
    description="Список назначений текущего пользователя.",
)
def my_assignments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Assignment)
        .filter(Assignment.user_id == current_user.id)
        .order_by(Assignment.created_at.desc())
    )

    return paginate(query, page, size)


@router.post(
    "",
    response_model=AssignmentRead,
    status_code=201,
    summary="Создать назначение",
    description="Назначить пользователю материал или тест.",
)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    user = get_or_404(db, User, payload.user_id)

    if not user.is_active:
        raise HTTPException(status_code=422, detail="Пользователь неактивен")

    if payload.material_id:
        get_or_404(db, Material, payload.material_id)

    if payload.test_id:
        get_or_404(db, Test, payload.test_id)

    assignment = Assignment(
        user_id=payload.user_id,
        material_id=payload.material_id,
        test_id=payload.test_id,
        assigned_by=current_user.id,
        due_date=payload.due_date,
        note=payload.note,
        status=AssignmentStatus.assigned,
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return assignment


@router.post(
    "/bulk",
    response_model=AssignmentBulkResult,
    status_code=201,
    summary="Массовое назначение",
    description="Назначить один материал или тест сразу нескольким активным пользователям.",
)
def bulk_assign(
    payload: AssignmentBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    if payload.material_id:
        get_or_404(db, Material, payload.material_id)

    if payload.test_id:
        get_or_404(db, Test, payload.test_id)

    users = (
        db.query(User)
        .filter(
            User.id.in_(payload.user_ids),
            User.is_active.is_(True),
        )
        .all()
    )

    if not users:
        raise HTTPException(
            status_code=404,
            detail="Активные пользователи не найдены",
        )

    for user in users:
        db.add(
            Assignment(
                user_id=user.id,
                material_id=payload.material_id,
                test_id=payload.test_id,
                assigned_by=current_user.id,
                due_date=payload.due_date,
                note=payload.note,
                status=AssignmentStatus.assigned,
            )
        )

    db.commit()

    return {"created": len(users)}


@router.get(
    "",
    response_model=Page[AssignmentRead],
    summary="Список назначений",
    description="Список назначений с фильтрами для HR/администратора.",
)
def list_assignments(
    user_id: UUID | None = Query(default=None, description="Фильтр по пользователю"),
    status: AssignmentStatus | None = Query(default=None, description="Фильтр по статусу"),
    overdue: bool = Query(default=False, description="Только просроченные"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    query = db.query(Assignment)

    if user_id:
        query = query.filter(Assignment.user_id == user_id)

    if status:
        query = query.filter(Assignment.status == status)

    if overdue:
        now = datetime.now(timezone.utc)
        query = query.filter(
            Assignment.due_date.isnot(None),
            Assignment.due_date < now,
            Assignment.status.notin_(
                [AssignmentStatus.completed, AssignmentStatus.canceled]
            ),
        )

    query = query.order_by(Assignment.created_at.desc())

    return paginate(query, page, size)


@router.get(
    "/{assignment_id}",
    response_model=AssignmentRead,
    summary="Получить назначение",
    description="Просмотр назначения по идентификатору.",
)
def get_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = get_or_404(db, Assignment, assignment_id)

    if current_user.id != assignment.user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    return assignment


@router.patch(
    "/{assignment_id}",
    response_model=AssignmentRead,
    summary="Обновить назначение",
    description="Изменить статус, срок или комментарий назначения.",
)
def update_assignment(
    assignment_id: UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    assignment = get_or_404(db, Assignment, assignment_id)
    data = payload.model_dump(exclude_unset=True)

    if "status" in data:
        if data["status"] == AssignmentStatus.completed and not assignment.completed_at:
            assignment.completed_at = datetime.now(timezone.utc)

        if data["status"] != AssignmentStatus.completed:
            assignment.completed_at = None

    for key, value in data.items():
        setattr(assignment, key, value)

    db.commit()
    db.refresh(assignment)

    return assignment


@router.post(
    "/{assignment_id}/start",
    response_model=AssignmentRead,
    summary="Начать выполнение",
    description="Пользователь переводит назначение в статус «в работе».",
)
def start_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = get_or_404(db, Assignment, assignment_id)

    if assignment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if assignment.status != AssignmentStatus.assigned:
        raise HTTPException(
            status_code=409,
            detail="Назначение нельзя начать в текущем статусе",
        )

    assignment.status = AssignmentStatus.in_progress
    db.commit()
    db.refresh(assignment)

    return assignment


@router.post(
    "/{assignment_id}/complete",
    response_model=AssignmentRead,
    summary="Завершить назначение",
    description=(
        "Для материала требуется хотя бы один просмотр. "
        "Для теста требуется пройденная попытка."
    ),
)
def complete_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assignment = get_or_404(db, Assignment, assignment_id)

    if assignment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    if assignment.status in (AssignmentStatus.completed, AssignmentStatus.canceled):
        raise HTTPException(
            status_code=409,
            detail="Назначение уже завершено или отменено",
        )

    if assignment.material_id:
        viewed = (
            db.query(MaterialView)
            .filter(
                MaterialView.material_id == assignment.material_id,
                MaterialView.user_id == current_user.id,
            )
            .first()
        )

        if not viewed:
            raise HTTPException(
                status_code=422,
                detail="Сначала откройте материал",
            )

    if assignment.test_id:
        passed_attempt = (
            db.query(TestAttempt)
            .filter(
                TestAttempt.test_id == assignment.test_id,
                TestAttempt.user_id == current_user.id,
                TestAttempt.status == AttemptStatus.completed,
                TestAttempt.passed.is_(True),
            )
            .first()
        )

        if not passed_attempt:
            raise HTTPException(
                status_code=422,
                detail="Для завершения нужно пройти тест",
            )

    assignment.status = AssignmentStatus.completed
    assignment.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(assignment)

    return assignment


@router.delete(
    "/{assignment_id}",
    status_code=204,
    summary="Удалить назначение",
    description="Удаляет назначение. Доступно только HR/администратору.",
)
def delete_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    assignment = get_or_404(db, Assignment, assignment_id)

    db.delete(assignment)
    db.commit()

    return None