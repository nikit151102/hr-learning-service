from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_current_user, get_or_404, paginate
from app.enterprise_models import (
    Course,
    CourseEnrollment,
    CourseEnrollmentStatus,
    CourseItem,
)
from app.enterprise_schemas import (
    CourseCreate,
    CourseEnrollmentBulkResult,
    CourseEnrollmentCreate,
    CourseEnrollmentProgressRead,
    CourseEnrollmentRead,
    CourseItemCreate,
    CourseItemRead,
    CourseItemUpdate,
    CourseRead,
    CourseUpdate,
)
from app.enterprise_services import recalculate_enrollment
from app.models import Material, Test, User, UserRole
from app.schemas import Page


router = APIRouter(prefix="/courses", tags=["Курсы"])


def _ensure_course_available(
    db: Session,
    course_id: UUID,
    current_user: User,
) -> Course:
    course = get_or_404(db, Course, course_id)

    if not course.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Курс не найден")

    return course


@router.get(
    "/my/enrollments",
    response_model=Page[CourseEnrollmentRead],
    summary="Мои курсы",
    description="Список курсов, назначенных текущему пользователю.",
)
def my_enrollments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.user_id == current_user.id)
        .order_by(CourseEnrollment.created_at.desc())
    )

    return paginate(query, page, size)


@router.post(
    "",
    response_model=CourseRead,
    status_code=201,
    summary="Создать курс",
    description="Создание учебного курса/плана обучения.",
)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    course = Course(
        **payload.model_dump(),
        created_by=current_user.id,
    )

    db.add(course)
    db.commit()
    db.refresh(course)

    return course


@router.get(
    "",
    response_model=Page[CourseRead],
    summary="Список курсов",
    description="Список курсов. Сотрудники видят только опубликованные.",
)
def list_courses(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Course)

    if current_user.role not in (UserRole.hr, UserRole.admin):
        query = query.filter(Course.is_published.is_(True))

    query = query.order_by(Course.created_at.desc())

    return paginate(query, page, size)


@router.get(
    "/{course_id}",
    response_model=CourseRead,
    summary="Получить курс",
    description="Карточка курса.",
)
def get_course(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _ensure_course_available(db, course_id, current_user)


@router.patch(
    "/{course_id}",
    response_model=CourseRead,
    summary="Обновить курс",
    description="Обновление названия, описания, публикации и обязательности курса.",
)
def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    course = get_or_404(db, Course, course_id)
    data = payload.model_dump(exclude_unset=True)

    for key, value in data.items():
        setattr(course, key, value)

    db.commit()
    db.refresh(course)

    return course


@router.delete(
    "/{course_id}",
    status_code=204,
    summary="Удалить курс",
    description="Удаляет курс, если по нему нет назначений.",
)
def delete_course(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    course = get_or_404(db, Course, course_id)

    enrollments_count = (
        db.query(func.count(CourseEnrollment.id))
        .filter(CourseEnrollment.course_id == course_id)
        .scalar()
        or 0
    )

    if enrollments_count:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить курс, по которому есть назначения",
        )

    db.delete(course)
    db.commit()

    return None


@router.post(
    "/{course_id}/items",
    response_model=CourseItemRead,
    status_code=201,
    summary="Добавить элемент курса",
    description="Добавить в курс материал или тест.",
)
def add_course_item(
    course_id: UUID,
    payload: CourseItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    course = get_or_404(db, Course, course_id)

    if payload.material_id:
        get_or_404(db, Material, payload.material_id)

    if payload.test_id:
        get_or_404(db, Test, payload.test_id)

    item = CourseItem(
        course_id=course.id,
        material_id=payload.material_id,
        test_id=payload.test_id,
        sort_order=payload.sort_order,
        is_required=payload.is_required,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


@router.get(
    "/{course_id}/items",
    response_model=list[CourseItemRead],
    summary="Элементы курса",
    description="Список материалов и тестов, входящих в курс.",
)
def list_course_items(
    course_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_course_available(db, course_id, current_user)

    return (
        db.query(CourseItem)
        .filter(CourseItem.course_id == course_id)
        .order_by(CourseItem.sort_order)
        .all()
    )


@router.patch(
    "/items/{item_id}",
    response_model=CourseItemRead,
    summary="Обновить элемент курса",
    description="Обновление элемента курса: порядок, обязательность, объект.",
)
def update_course_item(
    item_id: UUID,
    payload: CourseItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    item = get_or_404(db, CourseItem, item_id)
    data = payload.model_dump(exclude_unset=True)

    for key, value in data.items():
        setattr(item, key, value)

    db.flush()

    if bool(item.material_id) == bool(item.test_id):
        raise HTTPException(
            status_code=422,
            detail="У элемента курса должен быть ровно один объект: материал или тест",
        )

    db.commit()
    db.refresh(item)

    return item


@router.delete(
    "/items/{item_id}",
    status_code=204,
    summary="Удалить элемент курса",
    description="Удаляет материал или тест из курса.",
)
def delete_course_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    item = get_or_404(db, CourseItem, item_id)

    db.delete(item)
    db.commit()

    return None


@router.post(
    "/{course_id}/enrollments",
    response_model=CourseEnrollmentBulkResult,
    status_code=201,
    summary="Назначить курс",
    description="Массовое назначение курса пользователям.",
)
def enroll_users(
    course_id: UUID,
    payload: CourseEnrollmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    course = get_or_404(db, Course, course_id)

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

    created = 0
    updated = 0

    for user in users:
        enrollment = (
            db.query(CourseEnrollment)
            .filter(
                CourseEnrollment.course_id == course.id,
                CourseEnrollment.user_id == user.id,
            )
            .first()
        )

        if enrollment:
            enrollment.due_date = payload.due_date
            enrollment.note = payload.note
            updated += 1
        else:
            db.add(
                CourseEnrollment(
                    course_id=course.id,
                    user_id=user.id,
                    assigned_by=current_user.id,
                    status=CourseEnrollmentStatus.assigned,
                    due_date=payload.due_date,
                    note=payload.note,
                    progress_percent=0,
                )
            )
            created += 1

    db.commit()

    return {"created": created, "updated": updated}


@router.get(
    "/{course_id}/enrollments",
    response_model=Page[CourseEnrollmentRead],
    summary="Назначения курса",
    description="Список пользователей, назначенных на курс.",
)
def list_course_enrollments(
    course_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    get_or_404(db, Course, course_id)

    query = (
        db.query(CourseEnrollment)
        .filter(CourseEnrollment.course_id == course_id)
        .order_by(CourseEnrollment.created_at.desc())
    )

    return paginate(query, page, size)


@router.get(
    "/enrollments/{enrollment_id}/progress",
    response_model=CourseEnrollmentProgressRead,
    summary="Прогресс по курсу",
    description="Подробный прогресс пользователя по элементам курса.",
)
def enrollment_progress(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enrollment = get_or_404(db, CourseEnrollment, enrollment_id)

    if current_user.id != enrollment.user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    enrollment = recalculate_enrollment(db, enrollment)
    db.commit()
    db.refresh(enrollment)

    items = (
        db.query(CourseItem)
        .filter(CourseItem.course_id == enrollment.course_id)
        .order_by(CourseItem.sort_order)
        .all()
    )

    progress_map = {p.item_id: p for p in enrollment.progress}

    result_items = []

    for item in items:
        if item.material_id:
            object_type = "material"
            object_id = item.material_id
            object_title = item.material.title if item.material else None
        else:
            object_type = "test"
            object_id = item.test_id
            object_title = item.test.title if item.test else None

        progress = progress_map.get(item.id)

        result_items.append(
            {
                "item_id": item.id,
                "object_type": object_type,
                "object_id": object_id,
                "object_title": object_title,
                "is_required": item.is_required,
                "completed": bool(progress and progress.completed),
            }
        )

    return {
        "enrollment": enrollment,
        "items": result_items,
    }


@router.post(
    "/enrollments/{enrollment_id}/recalculate",
    response_model=CourseEnrollmentRead,
    summary="Пересчитать прогресс",
    description="Принудительно пересчитывает прогресс по курсу.",
)
def recalculate_enrollment_endpoint(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enrollment = get_or_404(db, CourseEnrollment, enrollment_id)

    if current_user.id != enrollment.user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    enrollment = recalculate_enrollment(db, enrollment)
    db.commit()
    db.refresh(enrollment)

    return enrollment