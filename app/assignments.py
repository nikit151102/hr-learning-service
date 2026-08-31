from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.deps import HRRequired, get_current_user, get_or_404, paginate
from app.ext_models import Assignment, AssignmentStatus
from app.ext_schemas import (
    AssignmentBulkCreate,
    AssignmentBulkResult,
    AssignmentCreate,
    AssignmentRead,
    AssignmentUpdate,
    AssignmentDetailRead,
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
from app.services.max_notification_service import max_notification_service


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

    material = None
    test = None

    if payload.material_id:
        material = get_or_404(db, Material, payload.material_id)

    if payload.test_id:
        test = get_or_404(db, Test, payload.test_id)

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

    # Отправляем уведомление пользователю
    due_date_str = None
    if payload.due_date:
        due_date_str = payload.due_date.strftime("%d.%m.%Y")

    max_notification_service.send_assignment_notification(
        user=user,
        material=material,
        test=test,
        due_date=due_date_str,
        note=payload.note
    )

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
    material = None
    test = None

    if payload.material_id:
        material = get_or_404(db, Material, payload.material_id)

    if payload.test_id:
        test = get_or_404(db, Test, payload.test_id)

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

    # Отправляем массовое уведомление
    due_date_str = None
    if payload.due_date:
        due_date_str = payload.due_date.strftime("%d.%m.%Y")

    max_notification_service.send_bulk_assignment_notification(
        users=users,
        material=material,
        test=test,
        due_date=due_date_str,
        note=payload.note
    )

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


@router.get(
    "/{assignment_id}/detail",
    response_model=AssignmentDetailRead,
    summary="Детальная информация о назначении",
    description="Полная информация с проверкой просмотра материала и прохождения теста.",
)
def get_assignment_detail(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    assignment = get_or_404(db, Assignment, assignment_id)

    # Получаем пользователя
    user = db.query(User).filter(User.id == assignment.user_id).first()

    # Проверяем просмотр материала
    material_viewed = False
    material_viewed_at = None
    if assignment.material_id:
        view = (
            db.query(MaterialView)
            .filter(
                MaterialView.material_id == assignment.material_id,
                MaterialView.user_id == assignment.user_id,
            )
            .order_by(MaterialView.viewed_at.desc())
            .first()
        )
        if view:
            material_viewed = True
            material_viewed_at = view.viewed_at

    # Проверяем прохождение теста
    test_passed = False
    test_passed_at = None
    test_score = None
    test_max_score = None
    test_grade = None
    if assignment.test_id:
        attempt = (
            db.query(TestAttempt)
            .filter(
                TestAttempt.test_id == assignment.test_id,
                TestAttempt.user_id == assignment.user_id,
                TestAttempt.status == AttemptStatus.completed,
            )
            .order_by(TestAttempt.completed_at.desc())
            .first()
        )
        if attempt:
            test_passed = attempt.passed or False
            test_passed_at = attempt.completed_at
            test_score = attempt.score
            test_max_score = attempt.max_score
            test_grade = attempt.grade_name

    return {
        "id": assignment.id,
        "user_id": assignment.user_id,
        "user_name": user.full_name if user else None,
        "user_id_max": user.id_max if user else None,
        "material_id": assignment.material_id,
        "test_id": assignment.test_id,
        "status": assignment.status,
        "due_date": assignment.due_date,
        "note": assignment.note,
        "created_at": assignment.created_at,
        "completed_at": assignment.completed_at,
        "material_viewed": material_viewed,
        "material_viewed_at": material_viewed_at,
        "test_passed": test_passed,
        "test_passed_at": test_passed_at,
        "test_score": test_score,
        "test_max_score": test_max_score,
        "test_grade": test_grade,
    }


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