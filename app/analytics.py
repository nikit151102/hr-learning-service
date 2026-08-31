import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import HRRequired, get_or_404
from app.ext_models import Assignment, AssignmentStatus, MaterialFeedback
from app.ext_schemas import (
    AnalyticsDashboard,
    AnalyticsSummary,
    AttemptsByDay,
    CategoryAnalytics,
    MaterialAnalytics,
    MaterialDetailAnalytics,
    QuestionDifficulty,
    TestAnalytics,
    TestDetailAnalytics,
    UserAnalytics,
    UserDetailsAnalytics,
    ViewsByDay,
)
from app.models import (
    AttemptStatus,
    Category,
    File,
    Material,
    MaterialView,
    Test,
    TestAttempt,
    TestAttemptAnswer,
    TestQuestion,
    User,
)


router = APIRouter(prefix="/analytics", tags=["Аналитика"])


def _to_float(value):
    return float(value) if value is not None else None


def _summary(db: Session) -> dict:
    now = datetime.now(timezone.utc)

    users_total = db.query(func.count(User.id)).scalar() or 0
    active_users = (
        db.query(func.count(User.id))
        .filter(User.is_active.is_(True))
        .scalar()
        or 0
    )

    materials_total = db.query(func.count(Material.id)).scalar() or 0
    published_materials = (
        db.query(func.count(Material.id))
        .filter(Material.is_published.is_(True))
        .scalar()
        or 0
    )

    categories_total = db.query(func.count(Category.id)).scalar() or 0

    tests_total = db.query(func.count(Test.id)).scalar() or 0
    published_tests = (
        db.query(func.count(Test.id))
        .filter(Test.is_published.is_(True))
        .scalar()
        or 0
    )

    attempts_total = db.query(func.count(TestAttempt.id)).scalar() or 0
    completed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(TestAttempt.status == AttemptStatus.completed)
        .scalar()
        or 0
    )
    passed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.passed.is_(True),
        )
        .scalar()
        or 0
    )

    views_total = int(
        db.query(func.coalesce(func.sum(Material.view_count), 0)).scalar() or 0
    )

    files_total = db.query(func.count(File.id)).scalar() or 0

    avg_score = _to_float(
        db.query(func.avg(TestAttempt.score))
        .filter(
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.score.isnot(None),
        )
        .scalar()
    )

    avg_percent = _to_float(
        db.query(
            func.avg(
                TestAttempt.score * 100.0 / func.nullif(TestAttempt.max_score, 0)
            )
        )
        .filter(
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.score.isnot(None),
            TestAttempt.max_score.isnot(None),
            TestAttempt.max_score > 0,
        )
        .scalar()
    )

    pass_rate = (
        round(passed_attempts * 100.0 / completed_attempts, 2)
        if completed_attempts
        else None
    )

    assignments_total = db.query(func.count(Assignment.id)).scalar() or 0
    completed_assignments = (
        db.query(func.count(Assignment.id))
        .filter(Assignment.status == AssignmentStatus.completed)
        .scalar()
        or 0
    )
    overdue_assignments = (
        db.query(func.count(Assignment.id))
        .filter(
            Assignment.status.notin_(
                [AssignmentStatus.completed, AssignmentStatus.canceled]
            ),
            Assignment.due_date.isnot(None),
            Assignment.due_date < now,
        )
        .scalar()
        or 0
    )

    avg_material_rating = _to_float(
        db.query(func.avg(MaterialFeedback.rating)).scalar()
    )

    return {
        "users_total": users_total,
        "active_users": active_users,
        "materials_total": materials_total,
        "published_materials": published_materials,
        "categories_total": categories_total,
        "tests_total": tests_total,
        "published_tests": published_tests,
        "attempts_total": attempts_total,
        "completed_attempts": completed_attempts,
        "passed_attempts": passed_attempts,
        "failed_attempts": completed_attempts - passed_attempts,
        "views_total": views_total,
        "files_total": files_total,
        "avg_score": avg_score,
        "avg_percent": avg_percent,
        "pass_rate": pass_rate,
        "assignments_total": assignments_total,
        "completed_assignments": completed_assignments,
        "overdue_assignments": overdue_assignments,
        "avg_material_rating": avg_material_rating,
    }


def _attempts_by_day(
    db: Session,
    days: int,
    test_id: UUID | None = None,
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    day_label = func.date_trunc("day", TestAttempt.started_at).label("day")

    query = db.query(
        day_label,
        func.count(TestAttempt.id).label("attempts"),
        func.sum(case((TestAttempt.passed.is_(True), 1), else_=0)).label("passed"),
        func.avg(TestAttempt.score).label("avg_score"),
    ).filter(
        TestAttempt.started_at >= since,
        TestAttempt.status == AttemptStatus.completed,
    )

    if test_id:
        query = query.filter(TestAttempt.test_id == test_id)

    rows = query.group_by(day_label).order_by(day_label).all()

    return [
        {
            "day": row.day.date(),
            "attempts": int(row.attempts or 0),
            "passed": int(row.passed or 0),
            "avg_score": _to_float(row.avg_score),
        }
        for row in rows
    ]


def _views_by_day(
    db: Session,
    days: int,
    material_id: UUID | None = None,
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    day_label = func.date_trunc("day", MaterialView.viewed_at).label("day")

    query = db.query(
        day_label,
        func.count(MaterialView.id).label("views"),
    ).filter(MaterialView.viewed_at >= since)

    if material_id:
        query = query.filter(MaterialView.material_id == material_id)

    rows = query.group_by(day_label).order_by(day_label).all()

    return [
        {
            "day": row.day.date(),
            "views": int(row.views or 0),
        }
        for row in rows
    ]


def _top_tests(db: Session, limit: int) -> list[dict]:
    sub = (
        db.query(
            TestAttempt.test_id.label("test_id"),
            func.count(TestAttempt.id).label("attempts"),
            func.sum(case((TestAttempt.passed.is_(True), 1), else_=0)).label("passed"),
            func.avg(TestAttempt.score).label("avg_score"),
        )
        .filter(TestAttempt.status == AttemptStatus.completed)
        .group_by(TestAttempt.test_id)
        .subquery()
    )

    rows = (
        db.query(
            Test.id,
            Test.title,
            sub.c.attempts,
            sub.c.passed,
            sub.c.avg_score,
        )
        .join(sub, Test.id == sub.c.test_id)
        .order_by(sub.c.attempts.desc())
        .limit(limit)
        .all()
    )

    result = []
    for row in rows:
        attempts = int(row.attempts or 0)
        passed = int(row.passed or 0)

        result.append(
            {
                "test_id": row.id,
                "title": row.title,
                "attempts": attempts,
                "passed": passed,
                "pass_rate": round(passed * 100.0 / attempts, 2) if attempts else 0.0,
                "avg_score": _to_float(row.avg_score),
            }
        )

    return result


def _top_materials(db: Session, limit: int) -> list[dict]:
    feedback_sub = (
        db.query(
            MaterialFeedback.material_id.label("material_id"),
            func.avg(MaterialFeedback.rating).label("avg_rating"),
            func.count(MaterialFeedback.id).label("feedback_count"),
        )
        .group_by(MaterialFeedback.material_id)
        .subquery()
    )

    rows = (
        db.query(
            Material.id,
            Material.title,
            Material.view_count,
            feedback_sub.c.avg_rating,
            feedback_sub.c.feedback_count,
        )
        .outerjoin(feedback_sub, Material.id == feedback_sub.c.material_id)
        .order_by(Material.view_count.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "material_id": row.id,
            "title": row.title,
            "views": int(row.view_count or 0),
            "avg_rating": _to_float(row.avg_rating),
            "feedback_count": int(row.feedback_count or 0),
        }
        for row in rows
    ]


def _top_users(db: Session, limit: int) -> list[dict]:
    attempts_sub = (
        db.query(
            TestAttempt.user_id.label("user_id"),
            func.count(TestAttempt.id).label("attempts"),
            func.sum(case((TestAttempt.passed.is_(True), 1), else_=0)).label("passed"),
            func.avg(TestAttempt.score).label("avg_score"),
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

    rows = (
        db.query(
            User.id,
            User.full_name,
            attempts_sub.c.attempts,
            attempts_sub.c.passed,
            attempts_sub.c.avg_score,
            func.coalesce(views_sub.c.views, 0).label("views"),
        )
        .join(attempts_sub, User.id == attempts_sub.c.user_id)
        .outerjoin(views_sub, User.id == views_sub.c.user_id)
        .order_by(attempts_sub.c.attempts.desc())
        .limit(limit)
        .all()
    )

    result = []
    for row in rows:
        attempts = int(row.attempts or 0)
        passed = int(row.passed or 0)

        result.append(
            {
                "user_id": row.id,
                "full_name": row.full_name,
                "attempts": attempts,
                "passed": passed,
                "pass_rate": round(passed * 100.0 / attempts, 2) if attempts else 0.0,
                "avg_score": _to_float(row.avg_score),
                "views": int(row.views or 0),
            }
        )

    return result


@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Общая сводка",
    description="Сводная статистика по пользователям, материалам, тестам, попыткам, просмотрам, назначениям и рейтингам.",
)
def analytics_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return _summary(db)


@router.get(
    "/dashboard",
    response_model=AnalyticsDashboard,
    summary="Дашборд администратора",
    description="Сводка + динамика + топы тестов, материалов и пользователей.",
)
def analytics_dashboard(
    days: int = Query(default=30, ge=1, le=365, description="Период в днях"),
    limit: int = Query(default=5, ge=1, le=50, description="Размер топов"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return {
        "summary": _summary(db),
        "attempts_by_day": _attempts_by_day(db, days),
        "views_by_day": _views_by_day(db, days),
        "top_tests": _top_tests(db, limit),
        "top_materials": _top_materials(db, limit),
        "top_users": _top_users(db, limit),
    }


@router.get(
    "/attempts/by-day",
    response_model=list[AttemptsByDay],
    summary="Попытки по дням",
    description="Динамика завершённых попыток по дням.",
)
def attempts_by_day(
    days: int = Query(default=30, ge=1, le=365, description="Период в днях"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return _attempts_by_day(db, days)


@router.get(
    "/materials/views-by-day",
    response_model=list[ViewsByDay],
    summary="Просмотры материалов по дням",
    description="Динамика просмотров материалов по дням.",
)
def material_views_by_day(
    days: int = Query(default=30, ge=1, le=365, description="Период в днях"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return _views_by_day(db, days)


@router.get(
    "/tests/top",
    response_model=list[TestAnalytics],
    summary="Топ тестов",
    description="Самые популярные тесты по количеству завершённых попыток.",
)
def top_tests(
    limit: int = Query(default=10, ge=1, le=100, description="Количество записей"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return _top_tests(db, limit)


@router.get(
    "/materials/top",
    response_model=list[MaterialAnalytics],
    summary="Топ материалов",
    description="Самые просматриваемые материалы с рейтингом и количеством отзывов.",
)
def top_materials(
    limit: int = Query(default=10, ge=1, le=100, description="Количество записей"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return _top_materials(db, limit)


@router.get(
    "/users/top",
    response_model=list[UserAnalytics],
    summary="Топ пользователей",
    description="Пользователи с наибольшей активностью по попыткам.",
)
def top_users(
    limit: int = Query(default=10, ge=1, le=100, description="Количество записей"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return _top_users(db, limit)


@router.get(
    "/questions/difficult",
    response_model=list[QuestionDifficulty],
    summary="Самые сложные вопросы",
    description="Вопросы с наименьшим средним процентом результата.",
)
def difficult_questions(
    limit: int = Query(default=10, ge=1, le=100, description="Количество записей"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    sub = (
        db.query(
            TestAttemptAnswer.question_id.label("question_id"),
            func.count(TestAttemptAnswer.id).label("answers"),
            func.avg(TestAttemptAnswer.score).label("avg_score"),
            func.avg(TestAttemptAnswer.max_score).label("avg_max"),
            func.sum(case((TestAttemptAnswer.score == 0, 1), else_=0)).label(
                "zero_count"
            ),
        )
        .join(TestAttempt, TestAttempt.id == TestAttemptAnswer.attempt_id)
        .filter(TestAttempt.status == AttemptStatus.completed)
        .group_by(TestAttemptAnswer.question_id)
        .subquery()
    )

    rows = (
        db.query(
            TestQuestion.id,
            TestQuestion.text,
            Test.title.label("test_title"),
            sub.c.answers,
            sub.c.avg_score,
            sub.c.avg_max,
            sub.c.zero_count,
        )
        .join(sub, TestQuestion.id == sub.c.question_id)
        .join(Test, TestQuestion.test_id == Test.id)
        .order_by(
            func.coalesce(
                sub.c.avg_score * 100.0 / func.nullif(sub.c.avg_max, 0),
                0,
            ).asc()
        )
        .limit(limit)
        .all()
    )

    result = []

    for row in rows:
        avg_score = _to_float(row.avg_score)
        avg_max = _to_float(row.avg_max)

        avg_percent = None
        if avg_score is not None and avg_max not in (None, 0):
            avg_percent = round(avg_score * 100.0 / avg_max, 2)

        zero_rate = None
        answers_count = int(row.answers or 0)
        if answers_count:
            zero_rate = round(int(row.zero_count or 0) * 100.0 / answers_count, 2)

        result.append(
            {
                "question_id": row.id,
                "text": row.text,
                "test_title": row.test_title,
                "answers_count": answers_count,
                "avg_score": avg_score,
                "avg_percent": avg_percent,
                "zero_rate": zero_rate,
            }
        )

    return result


@router.get(
    "/categories/summary",
    response_model=list[CategoryAnalytics],
    summary="Статистика по категориям",
    description="Количество материалов и суммарные просмотры по категориям.",
)
def categories_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    rows = (
        db.query(
            Category.id,
            Category.name,
            func.count(Material.id).label("materials"),
            func.coalesce(func.sum(Material.view_count), 0).label("views"),
        )
        .outerjoin(Material, Material.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(func.count(Material.id).desc())
        .all()
    )

    return [
        {
            "category_id": row.id,
            "name": row.name,
            "materials": int(row.materials or 0),
            "views": int(row.views or 0),
        }
        for row in rows
    ]


@router.get(
    "/tests/{test_id}",
    response_model=TestDetailAnalytics,
    summary="Аналитика по тесту",
    description="Подробная статистика по конкретному тесту.",
)
def test_analytics_detail(
    test_id: UUID,
    days: int = Query(default=30, ge=1, le=365, description="Период в днях"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)

    attempts_total = (
        db.query(func.count(TestAttempt.id))
        .filter(TestAttempt.test_id == test_id)
        .scalar()
        or 0
    )

    completed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.test_id == test_id,
            TestAttempt.status == AttemptStatus.completed,
        )
        .scalar()
        or 0
    )

    passed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.test_id == test_id,
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.passed.is_(True),
        )
        .scalar()
        or 0
    )

    avg_score = _to_float(
        db.query(func.avg(TestAttempt.score))
        .filter(
            TestAttempt.test_id == test_id,
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.score.isnot(None),
        )
        .scalar()
    )

    grade_label = func.coalesce(TestAttempt.grade_name, "Без градации").label(
        "grade_name"
    )

    grade_rows = (
        db.query(
            grade_label,
            func.count(TestAttempt.id).label("count"),
        )
        .filter(
            TestAttempt.test_id == test_id,
            TestAttempt.status == AttemptStatus.completed,
        )
        .group_by(grade_label)
        .all()
    )

    return {
        "test": test,
        "attempts_total": attempts_total,
        "completed_attempts": completed_attempts,
        "passed_attempts": passed_attempts,
        "pass_rate": (
            round(passed_attempts * 100.0 / completed_attempts, 2)
            if completed_attempts
            else None
        ),
        "avg_score": avg_score,
        "attempts_by_day": _attempts_by_day(db, days, test_id),
        "grade_distribution": [
            {
                "grade_name": row.grade_name,
                "count": int(row.count or 0),
            }
            for row in grade_rows
        ],
    }


@router.get(
    "/materials/{material_id}",
    response_model=MaterialDetailAnalytics,
    summary="Аналитика по материалу",
    description="Подробная статистика по конкретному материалу.",
)
def material_analytics_detail(
    material_id: UUID,
    days: int = Query(default=30, ge=1, le=365, description="Период в днях"),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    material = get_or_404(db, Material, material_id)

    unique_viewers = (
        db.query(func.count(func.distinct(MaterialView.user_id)))
        .filter(
            MaterialView.material_id == material_id,
            MaterialView.user_id.isnot(None),
        )
        .scalar()
        or 0
    )

    avg_rating = _to_float(
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
        "material": material,
        "views_total": int(material.view_count or 0),
        "unique_viewers": int(unique_viewers),
        "avg_rating": avg_rating,
        "feedback_count": int(feedback_count),
        "views_by_day": _views_by_day(db, days, material_id),
    }


@router.get(
    "/users/{user_id}",
    response_model=UserDetailsAnalytics,
    summary="Аналитика по пользователю",
    description="Подробная статистика по конкретному пользователю.",
)
def user_analytics_detail(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    user = get_or_404(db, User, user_id)
    now = datetime.now(timezone.utc)

    attempts_total = (
        db.query(func.count(TestAttempt.id))
        .filter(TestAttempt.user_id == user_id)
        .scalar()
        or 0
    )

    completed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.user_id == user_id,
            TestAttempt.status == AttemptStatus.completed,
        )
        .scalar()
        or 0
    )

    passed_attempts = (
        db.query(func.count(TestAttempt.id))
        .filter(
            TestAttempt.user_id == user_id,
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.passed.is_(True),
        )
        .scalar()
        or 0
    )

    avg_score = _to_float(
        db.query(func.avg(TestAttempt.score))
        .filter(
            TestAttempt.user_id == user_id,
            TestAttempt.status == AttemptStatus.completed,
            TestAttempt.score.isnot(None),
        )
        .scalar()
    )

    views_total = (
        db.query(func.count(MaterialView.id))
        .filter(MaterialView.user_id == user_id)
        .scalar()
        or 0
    )

    assignments_total = (
        db.query(func.count(Assignment.id))
        .filter(Assignment.user_id == user_id)
        .scalar()
        or 0
    )

    completed_assignments = (
        db.query(func.count(Assignment.id))
        .filter(
            Assignment.user_id == user_id,
            Assignment.status == AssignmentStatus.completed,
        )
        .scalar()
        or 0
    )

    overdue_assignments = (
        db.query(func.count(Assignment.id))
        .filter(
            Assignment.user_id == user_id,
            Assignment.status.notin_(
                [AssignmentStatus.completed, AssignmentStatus.canceled]
            ),
            Assignment.due_date.isnot(None),
            Assignment.due_date < now,
        )
        .scalar()
        or 0
    )

    last_attempts = (
        db.query(TestAttempt)
        .filter(TestAttempt.user_id == user_id)
        .order_by(TestAttempt.started_at.desc())
        .limit(10)
        .all()
    )

    return {
        "user": user,
        "attempts_total": attempts_total,
        "completed_attempts": completed_attempts,
        "passed_attempts": passed_attempts,
        "avg_score": avg_score,
        "views_total": int(views_total),
        "assignments_total": assignments_total,
        "completed_assignments": completed_assignments,
        "overdue_assignments": overdue_assignments,
        "last_attempts": last_attempts,
    }


@router.get(
    "/export/attempts.csv",
    summary="Экспорт попыток в CSV",
    description="Выгружает все попытки пользователей в CSV-файл.",
)
def export_attempts_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    rows = (
        db.query(TestAttempt, User.full_name, User.id_max, Test.title)
        .join(User, User.id == TestAttempt.user_id)
        .join(Test, Test.id == TestAttempt.test_id)
        .order_by(TestAttempt.started_at.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow(
        [
            "ID попытки",
            "Дата начала",
            "ФИО",
            "ID сотрудника",
            "Тест",
            "Статус",
            "Балл",
            "Макс. балл",
            "Проходной балл",
            "Пройден",
            "Градация",
        ]
    )

    for attempt, full_name, id_max, test_title in rows:
        writer.writerow(
            [
                str(attempt.id),
                attempt.started_at.isoformat() if attempt.started_at else "",
                full_name,
                id_max,
                test_title,
                attempt.status.value,
                attempt.score if attempt.score is not None else "",
                attempt.max_score if attempt.max_score is not None else "",
                attempt.passing_score if attempt.passing_score is not None else "",
                "Да" if attempt.passed else "Нет",
                attempt.grade_name or "",
            ]
        )

    content = output.getvalue().encode("utf-8-sig")

    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=attempts.csv",
        },
    )