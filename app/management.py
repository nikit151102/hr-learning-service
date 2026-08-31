from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, exists, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_current_user, get_or_404, paginate
from app.enterprise_models import (
    CourseEnrollment,
    CourseEnrollmentStatus,
    EmployeeDepartment,
    ManagerRight,
    MandatoryTest,
    Certificate,
)
from app.enterprise_schemas import (
    EmployeeDepartmentRead,
    EmployeeDepartmentSet,
    ManagerDashboard,
    ManagerRightCreate,
    ManagerRightRead,
    MandatoryRiskItem,
    MandatoryTestCreate,
    MandatoryTestRead,
    OverdueItem,
    UserProgressItem,
)
from app.enterprise_services import get_manager_department
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
from app.schemas import Page


router = APIRouter(prefix="/management", tags=["Управление"])


# ==================== MANAGERS ====================

@router.post(
    "/managers",
    response_model=ManagerRightRead,
    summary="Назначить руководителя",
    description="Выдать пользователю права руководителя отдела или всех отделов.",
)
def grant_manager(
    payload: ManagerRightCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    get_or_404(db, User, payload.user_id)

    existing = (
        db.query(ManagerRight)
        .filter(ManagerRight.user_id == payload.user_id)
        .first()
    )

    if existing:
        existing.department = payload.department
        manager_right = existing
    else:
        manager_right = ManagerRight(
            user_id=payload.user_id,
            department=payload.department,
        )
        db.add(manager_right)

    db.commit()
    db.refresh(manager_right)

    return manager_right


@router.get(
    "/managers",
    response_model=Page[ManagerRightRead],
    summary="Список руководителей",
    description="Список пользователей с правами руководителя.",
)
def list_managers(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    query = db.query(ManagerRight).order_by(ManagerRight.created_at.desc())
    return paginate(query, page, size)


@router.delete(
    "/managers/{user_id}",
    status_code=204,
    summary="Снять права руководителя",
    description="Удаляет права руководителя у пользователя.",
)
def revoke_manager(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    manager_right = (
        db.query(ManagerRight)
        .filter(ManagerRight.user_id == user_id)
        .first()
    )

    if not manager_right:
        raise HTTPException(status_code=404, detail="Права руководителя не найдены")

    db.delete(manager_right)
    db.commit()

    return None


# ==================== EMPLOYEE DEPARTMENTS ====================

@router.post(
    "/employee-departments",
    response_model=EmployeeDepartmentRead,
    summary="Указать отдел сотрудника",
    description="Устанавливает отдел для сотрудника.",
)
def set_employee_department(
    payload: EmployeeDepartmentSet,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    get_or_404(db, User, payload.user_id)

    existing = (
        db.query(EmployeeDepartment)
        .filter(EmployeeDepartment.user_id == payload.user_id)
        .first()
    )

    if existing:
        existing.department = payload.department
        employee_department = existing
    else:
        employee_department = EmployeeDepartment(
            user_id=payload.user_id,
            department=payload.department,
        )
        db.add(employee_department)

    db.commit()
    db.refresh(employee_department)

    return employee_department


@router.get(
    "/employee-departments",
    response_model=Page[EmployeeDepartmentRead],
    summary="Отделы сотрудников",
    description="Список привязок сотрудников к отделам.",
)
def list_employee_departments(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    query = db.query(EmployeeDepartment).order_by(EmployeeDepartment.department)
    return paginate(query, page, size)


# ==================== MANDATORY TESTS ====================

@router.post(
    "/mandatory-tests",
    response_model=MandatoryTestRead,
    summary="Сделать тест обязательным",
    description="Добавляет тест в список обязательных.",
)
def add_mandatory_test(
    payload: MandatoryTestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, payload.test_id)

    existing = (
        db.query(MandatoryTest)
        .filter(MandatoryTest.test_id == test.id)
        .first()
    )

    if existing:
        return existing

    mandatory_test = MandatoryTest(
        test_id=test.id,
        created_by=current_user.id,
    )

    db.add(mandatory_test)
    db.commit()
    db.refresh(mandatory_test)

    return mandatory_test


@router.get(
    "/mandatory-tests",
    response_model=Page[MandatoryTestRead],
    summary="Обязательные тесты",
    description="Список обязательных тестов.",
)
def list_mandatory_tests(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    query = db.query(MandatoryTest).order_by(MandatoryTest.created_at.desc())
    return paginate(query, page, size)


@router.delete(
    "/mandatory-tests/{test_id}",
    status_code=204,
    summary="Убрать обязательность теста",
    description="Удаляет тест из списка обязательных.",
)
def delete_mandatory_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    mandatory_test = (
        db.query(MandatoryTest)
        .filter(MandatoryTest.test_id == test_id)
        .first()
    )

    if not mandatory_test:
        raise HTTPException(status_code=404, detail="Обязательный тест не найден")

    db.delete(mandatory_test)
    db.commit()

    return None


# ==================== DASHBOARD ====================

@router.get(
    "/dashboard",
    response_model=ManagerDashboard,
    summary="Дашборд руководителя",
    description="Сводная статистика по отделу или всей компании.",
)
def manager_dashboard(
    department: str | None = Query(default=None, description="Отдел"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    department = get_manager_department(db, current_user, department)
    now = datetime.now(timezone.utc)

    users_query = db.query(User).outerjoin(
        EmployeeDepartment,
        EmployeeDepartment.user_id == User.id,
    )

    if department:
        users_query = users_query.filter(EmployeeDepartment.department == department)

    users_total = users_query.count()
    active_users = users_query.filter(User.is_active.is_(True)).count()

    attempts_query = (
        db.query(
            func.count(TestAttempt.id).label("completed"),
            func.sum(case((TestAttempt.passed.is_(True), 1), else_=0)).label("passed"),
        )
        .join(User, User.id == TestAttempt.user_id)
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
        .filter(TestAttempt.status == AttemptStatus.completed)
    )

    if department:
        attempts_query = attempts_query.filter(
            EmployeeDepartment.department == department
        )

    attempts_row = attempts_query.one()
    completed_attempts = int(attempts_row.completed or 0)
    passed_attempts = int(attempts_row.passed or 0)

    overdue_assignments_query = (
        db.query(func.count(Assignment.id))
        .join(User, User.id == Assignment.user_id)
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
        .filter(
            Assignment.due_date.isnot(None),
            Assignment.due_date < now,
            Assignment.status.notin_(
                [AssignmentStatus.completed, AssignmentStatus.canceled]
            ),
        )
    )

    if department:
        overdue_assignments_query = overdue_assignments_query.filter(
            EmployeeDepartment.department == department
        )

    overdue_assignments = int(overdue_assignments_query.scalar() or 0)

    overdue_course_query = (
        db.query(func.count(CourseEnrollment.id))
        .join(User, User.id == CourseEnrollment.user_id)
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
        .filter(
            CourseEnrollment.due_date.isnot(None),
            CourseEnrollment.due_date < now,
            CourseEnrollment.status.notin_(
                [
                    CourseEnrollmentStatus.completed,
                    CourseEnrollmentStatus.canceled,
                ]
            ),
        )
    )

    if department:
        overdue_course_query = overdue_course_query.filter(
            EmployeeDepartment.department == department
        )

    overdue_course_enrollments = int(overdue_course_query.scalar() or 0)

    mandatory_tests_total = (
        db.query(func.count(MandatoryTest.id))
        .join(Test, Test.id == MandatoryTest.test_id)
        .filter(Test.is_published.is_(True))
        .scalar()
        or 0
    )

    mandatory_tests = (
        db.query(Test.id, Test.title)
        .join(MandatoryTest, MandatoryTest.test_id == Test.id)
        .filter(Test.is_published.is_(True))
        .all()
    )

    passed_sub = (
        db.query(
            TestAttempt.user_id.label("user_id"),
            TestAttempt.test_id.label("test_id"),
        )
        .filter(
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.passed.is_(True),
        )
        .distinct()
        .subquery()
    )

    mandatory_not_passed_pairs = 0

    for test_id, _ in mandatory_tests:
        q = (
            db.query(User.id)
            .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
            .filter(
                User.is_active.is_(True),
                ~exists().where(
                    and_(
                        passed_sub.c.user_id == User.id,
                        passed_sub.c.test_id == test_id,
                    )
                ),
            )
        )

        if department:
            q = q.filter(EmployeeDepartment.department == department)

        mandatory_not_passed_pairs += q.count()

    certificates_query = (
        db.query(func.count(Certificate.id))
        .join(User, User.id == Certificate.user_id)
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
    )

    if department:
        certificates_query = certificates_query.filter(
            EmployeeDepartment.department == department
        )

    certificates_total = int(certificates_query.scalar() or 0)

    avg_course_progress_query = (
        db.query(func.avg(CourseEnrollment.progress_percent))
        .join(User, User.id == CourseEnrollment.user_id)
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
        .filter(CourseEnrollment.status != CourseEnrollmentStatus.canceled)
    )

    if department:
        avg_course_progress_query = avg_course_progress_query.filter(
            EmployeeDepartment.department == department
        )

    avg_course_progress_raw = avg_course_progress_query.scalar()
    avg_course_progress = (
        float(avg_course_progress_raw) if avg_course_progress_raw is not None else None
    )

    return {
        "department": department,
        "users_total": users_total,
        "active_users": active_users,
        "completed_attempts": completed_attempts,
        "passed_attempts": passed_attempts,
        "pass_rate": (
            round(passed_attempts * 100.0 / completed_attempts, 2)
            if completed_attempts
            else None
        ),
        "overdue_assignments": overdue_assignments,
        "overdue_course_enrollments": overdue_course_enrollments,
        "mandatory_tests_total": int(mandatory_tests_total),
        "mandatory_not_passed_pairs": mandatory_not_passed_pairs,
        "certificates_total": certificates_total,
        "avg_course_progress": avg_course_progress,
    }


@router.get(
    "/mandatory-risks",
    response_model=list[MandatoryRiskItem],
    summary="Риски по обязательным тестам",
    description="Сотрудники, которые ещё не прошли обязательные опубликованные тесты.",
)
def mandatory_risks(
    department: str | None = Query(default=None, description="Отдел"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    department = get_manager_department(db, current_user, department)

    mandatory_tests = (
        db.query(Test.id, Test.title)
        .join(MandatoryTest, MandatoryTest.test_id == Test.id)
        .filter(Test.is_published.is_(True))
        .all()
    )

    passed_sub = (
        db.query(
            TestAttempt.user_id.label("user_id"),
            TestAttempt.test_id.label("test_id"),
        )
        .filter(
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.passed.is_(True),
        )
        .distinct()
        .subquery()
    )

    result = []

    for test_id, test_title in mandatory_tests:
        q = (
            db.query(User.id, User.full_name, EmployeeDepartment.department)
            .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
            .filter(
                User.is_active.is_(True),
                ~exists().where(
                    and_(
                        passed_sub.c.user_id == User.id,
                        passed_sub.c.test_id == test_id,
                    )
                ),
            )
        )

        if department:
            q = q.filter(EmployeeDepartment.department == department)

        rows = q.limit(limit).all()

        for row in rows:
            result.append(
                {
                    "user_id": row.id,
                    "full_name": row.full_name,
                    "department": row.department,
                    "test_id": test_id,
                    "test_title": test_title,
                }
            )

        if len(result) >= limit:
            break

    return result[:limit]


@router.get(
    "/overdue",
    response_model=list[OverdueItem],
    summary="Просроченные назначения",
    description="Просроченные назначения и курсы по отделу или компании.",
)
def overdue_items(
    department: str | None = Query(default=None, description="Отдел"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    department = get_manager_department(db, current_user, department)
    now = datetime.now(timezone.utc)

    result = []

    assignments_query = (
        db.query(
            Assignment.id,
            Assignment.user_id,
            Assignment.due_date,
            Assignment.material_id,
            Assignment.test_id,
            User.full_name,
            EmployeeDepartment.department,
            Material.title.label("material_title"),
            Test.title.label("test_title"),
        )
        .join(User, User.id == Assignment.user_id)
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
        .outerjoin(Material, Material.id == Assignment.material_id)
        .outerjoin(Test, Test.id == Assignment.test_id)
        .filter(
            Assignment.due_date.isnot(None),
            Assignment.due_date < now,
            Assignment.status.notin_(
                [AssignmentStatus.completed, AssignmentStatus.canceled]
            ),
        )
    )

    if department:
        assignments_query = assignments_query.filter(
            EmployeeDepartment.department == department
        )

    for row in assignments_query.limit(limit).all():
        object_type = "material" if row.material_id else "test"
        object_id = row.material_id or row.test_id
        title = row.material_title or row.test_title

        result.append(
            {
                "id": row.id,
                "kind": "assignment",
                "user_id": row.user_id,
                "full_name": row.full_name,
                "department": row.department,
                "object_type": object_type,
                "object_id": object_id,
                "title": title,
                "due_date": row.due_date,
            }
        )

    courses_query = (
        db.query(
            CourseEnrollment.id,
            CourseEnrollment.user_id,
            CourseEnrollment.due_date,
            CourseEnrollment.course_id,
            User.full_name,
            EmployeeDepartment.department,
        )
        .join(User, User.id == CourseEnrollment.user_id)
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
        .filter(
            CourseEnrollment.due_date.isnot(None),
            CourseEnrollment.due_date < now,
            CourseEnrollment.status.notin_(
                [
                    CourseEnrollmentStatus.completed,
                    CourseEnrollmentStatus.canceled,
                ]
            ),
        )
    )

    if department:
        courses_query = courses_query.filter(
            EmployeeDepartment.department == department
        )

    from app.enterprise_models import Course

    for row in courses_query.limit(limit).all():
        course = db.get(Course, row.course_id)

        result.append(
            {
                "id": row.id,
                "kind": "course_enrollment",
                "user_id": row.user_id,
                "full_name": row.full_name,
                "department": row.department,
                "object_type": "course",
                "object_id": row.course_id,
                "title": course.title if course else None,
                "due_date": row.due_date,
            }
        )

    return result[:limit]


@router.get(
    "/users-progress",
    response_model=list[UserProgressItem],
    summary="Прогресс сотрудников",
    description="Сводный прогресс сотрудников по обучению и тестам.",
)
def users_progress(
    department: str | None = Query(default=None, description="Отдел"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    department = get_manager_department(db, current_user, department)

    attempts_sub = (
        db.query(
            TestAttempt.user_id.label("user_id"),
            func.count(TestAttempt.id).label("completed_attempts"),
            func.sum(case((TestAttempt.passed.is_(True), 1), else_=0)).label(
                "passed_attempts"
            ),
        )
        .filter(TestAttempt.status == AttemptStatus.completed)
        .group_by(TestAttempt.user_id)
        .subquery()
    )

    views_sub = (
        db.query(
            MaterialView.user_id.label("user_id"),
            func.count(MaterialView.id).label("views"),
        )
        .group_by(MaterialView.user_id)
        .subquery()
    )

    assignments_sub = (
        db.query(
            Assignment.user_id.label("user_id"),
            func.count(Assignment.id).label("assignments_total"),
            func.sum(case((Assignment.status == AssignmentStatus.completed, 1), else_=0)).label(
                "assignments_completed"
            ),
        )
        .group_by(Assignment.user_id)
        .subquery()
    )

    courses_sub = (
        db.query(
            CourseEnrollment.user_id.label("user_id"),
            func.count(CourseEnrollment.id).label("course_total"),
            func.sum(
                case((CourseEnrollment.status == CourseEnrollmentStatus.completed, 1), else_=0)
            ).label("course_completed"),
            func.avg(CourseEnrollment.progress_percent).label("avg_progress"),
        )
        .group_by(CourseEnrollment.user_id)
        .subquery()
    )

    query = (
        db.query(
            User.id,
            User.full_name,
            EmployeeDepartment.department,
            func.coalesce(attempts_sub.c.completed_attempts, 0).label("completed_attempts"),
            func.coalesce(attempts_sub.c.passed_attempts, 0).label("passed_attempts"),
            func.coalesce(views_sub.c.views, 0).label("views"),
            func.coalesce(assignments_sub.c.assignments_total, 0).label("assignments_total"),
            func.coalesce(assignments_sub.c.assignments_completed, 0).label(
                "assignments_completed"
            ),
            func.coalesce(courses_sub.c.course_total, 0).label("course_enrollments_total"),
            func.coalesce(courses_sub.c.course_completed, 0).label(
                "course_enrollments_completed"
            ),
            courses_sub.c.avg_progress.label("avg_course_progress"),
        )
        .outerjoin(EmployeeDepartment, EmployeeDepartment.user_id == User.id)
        .outerjoin(attempts_sub, attempts_sub.c.user_id == User.id)
        .outerjoin(views_sub, views_sub.c.user_id == User.id)
        .outerjoin(assignments_sub, assignments_sub.c.user_id == User.id)
        .outerjoin(courses_sub, courses_sub.c.user_id == User.id)
        .filter(User.is_active.is_(True))
    )

    if department:
        query = query.filter(EmployeeDepartment.department == department)

    rows = query.order_by(User.full_name).limit(limit).all()

    return [
        {
            "user_id": row.id,
            "full_name": row.full_name,
            "department": row.department,
            "completed_attempts": int(row.completed_attempts or 0),
            "passed_attempts": int(row.passed_attempts or 0),
            "views": int(row.views or 0),
            "assignments_total": int(row.assignments_total or 0),
            "assignments_completed": int(row.assignments_completed or 0),
            "course_enrollments_total": int(row.course_enrollments_total or 0),
            "course_enrollments_completed": int(row.course_enrollments_completed or 0),
            "avg_course_progress": (
                float(row.avg_course_progress)
                if row.avg_course_progress is not None
                else None
            ),
        }
        for row in rows
    ]