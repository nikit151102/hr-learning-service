import random
from uuid import UUID

from fastapi import APIRouter, Depends, File as FileField, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import case, exists, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.deps import (
    AdminRequired,
    HRRequired,
    get_by_id_max_or_create,
    get_current_user,
    get_or_404,
    paginate,
)
from app.models import (
    AttemptStatus,
    Category,
    File as FileModel,
    Material,
    MaterialView,
    QuestionType,
    Test,
    TestAnswerOption,
    TestAttempt,
    TestGrade,
    TestQuestion,
    User,
    UserRole,
    TestAttemptAnswer
)
from app.schemas import (
    AnswerOptionCreate,
    AnswerOptionPublic,
    AnswerOptionRead,
    AnswerOptionUpdate,
    AttemptAccess,
    AttemptRead,
    AttemptStartRead,
    AttemptSubmit,
    AttemptDetailRead,
    AttemptQuestionDetail,
    AttemptAnswerOptionDetail,
    CategoryContents,
    CategoryCreate,
    CategoryRead,
    CategoryTree,
    CategoryUpdate,
    FileRead,
    GradeCreate,
    GradeRead,
    GradeUpdate,
    LocationCreate,     
    LocationRead,         
    LocationUpdate,       
    LoginRequest,
    MaterialCreate,
    MaterialRead,
    MaterialReadWithUrl,
    MaterialSummary,
    MaterialUpdate,
    Page,
    QuestionCreate,
    QuestionPublic,
    QuestionRead,
    QuestionUpdate,
    TestCreate,
    TestFullRead,
    TestRead,
    TestSummary,
    TestUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.services import category_service, minio_service, test_service
from app.models import Location, LocationType

router = APIRouter(prefix="/api/v1")


# ==================== HEALTH ====================

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            {"status": "db_fail", "detail": str(exc)},
            status_code=503,
        )
    finally:
        db.close()

    try:
        minio_service.client.bucket_exists(settings.minio_bucket)
    except Exception as exc:
        return JSONResponse(
            {"status": "minio_fail", "detail": str(exc)},
            status_code=503,
        )

    return {"status": "ok"}


# ==================== AUTH ====================

@router.post("/auth/login", response_model=UserRead)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = get_by_id_max_or_create(db, payload.id_max)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    return user


@router.get("/auth/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return current_user


# ==================== USERS ====================

@router.post("/users", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    if payload.role == UserRole.admin and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Only admin can create admins")

    exists = db.query(User).filter(User.id_max == payload.id_max).first()
    if exists:
        raise HTTPException(status_code=409, detail="id_max already exists")

    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.get("/users", response_model=Page[UserRead])
def list_users(
    search: str | None = None,
    id_max: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    query = db.query(User)

    if id_max:
        query = query.filter(User.id_max == id_max)

    if search:
        query = query.filter(
            or_(
                User.id_max.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(User.created_at.desc())
    return paginate(query, page, size)


@router.get("/users/by-id-max/{id_max}", response_model=UserRead)
def get_user_by_id_max(
    id_max: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    user = db.query(User).filter(User.id_max == id_max).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    return get_or_404(db, User, user_id)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    user = get_or_404(db, User, user_id)
    data = payload.model_dump(exclude_unset=True)

    if "role" in data and data["role"] == UserRole.admin and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Only admin can assign admin role")

    if "id_max" in data and data["id_max"] != user.id_max:
        exists = db.query(User).filter(User.id_max == data["id_max"]).first()
        if exists:
            raise HTTPException(status_code=409, detail="id_max already exists")

    for key, value in data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)

    return user


@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)

    for field in ("full_name", "gender"):
        if field in data:
            setattr(current_user, field, data[field])

    db.commit()
    db.refresh(current_user)

    return current_user


# ==================== CATEGORIES ====================

@router.post("/categories", response_model=CategoryRead, status_code=201)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    category_service.assert_parent_exists(db, payload.parent_id)
    category_service.assert_name_unique(db, payload.parent_id, payload.name)

    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)

    return category


@router.get("/categories/tree", response_model=list[CategoryTree])
def category_tree(
    parent_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return category_service.build_tree(db, parent_id)


@router.get("/categories/{category_id}/contents", response_model=CategoryContents)
def category_contents(
    category_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    category = get_or_404(db, Category, category_id)

    subcategories = (
        db.query(Category)
        .filter(Category.parent_id == category_id)
        .order_by(Category.sort_order, Category.name)
        .all()
    )

    materials_query = db.query(Material).filter(Material.category_id == category_id)

    if current_user.role not in (UserRole.hr, UserRole.admin):
        materials_query = materials_query.filter(Material.is_published.is_(True))

    materials_query = materials_query.order_by(Material.sort_order, Material.title)
    materials_page = paginate(materials_query, page, size)

    return CategoryContents(
        category=category,
        subcategories=subcategories,
        materials=materials_page,
    )


@router.get("/categories/{category_id}", response_model=CategoryRead)
def get_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_or_404(db, Category, category_id)


@router.patch("/categories/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    category = get_or_404(db, Category, category_id)
    data = payload.model_dump(exclude_unset=True)

    if "parent_id" in data:
        category_service.assert_parent_exists(db, data["parent_id"])
        category_service.ensure_no_cycle(db, category.id, data["parent_id"])

    if "name" in data:
        parent_id = data.get("parent_id", category.parent_id)
        category_service.assert_name_unique(
            db,
            parent_id,
            data["name"],
            exclude_id=category.id,
        )

    for key, value in data.items():
        setattr(category, key, value)

    db.commit()
    db.refresh(category)

    return category


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    category = get_or_404(db, Category, category_id)

    children_count = (
        db.query(func.count(Category.id))
        .filter(Category.parent_id == category.id)
        .scalar()
        or 0
    )

    materials_count = (
        db.query(func.count(Material.id))
        .filter(Material.category_id == category.id)
        .scalar()
        or 0
    )

    if children_count or materials_count:
        raise HTTPException(
            status_code=409,
            detail="Category has children or materials",
        )

    db.delete(category)
    db.commit()

    return None


# ==================== FILES ====================

@router.post("/files/upload", response_model=FileRead, status_code=201)
def upload_file(
    file: UploadFile = FileField(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    db_file = minio_service.upload_file(db, file, current_user.id)
    db.commit()
    db.refresh(db_file)

    return db_file


# ==================== MATERIALS ====================

@router.post("/materials", response_model=MaterialRead, status_code=201)
def create_material(
    payload: MaterialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    get_or_404(db, Category, payload.category_id)

    if payload.file_id:
        get_or_404(db, FileModel, payload.file_id)

    if payload.test_id:
        get_or_404(db, Test, payload.test_id)

    material = Material(**payload.model_dump(), created_by=current_user.id)

    db.add(material)
    db.commit()
    db.refresh(material)

    return material


@router.get("/materials", response_model=Page[MaterialRead])
def list_materials(
    category_id: UUID | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Material)

    if current_user.role not in (UserRole.hr, UserRole.admin):
        query = query.filter(Material.is_published.is_(True))

    if category_id:
        query = query.filter(Material.category_id == category_id)

    if search:
        query = query.filter(
            or_(
                Material.title.ilike(f"%{search}%"),
                Material.description.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Material.sort_order, Material.title)
    return paginate(query, page, size)


@router.get("/materials/{material_id}", response_model=MaterialReadWithUrl)
def get_material(
    material_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    material = get_or_404(db, Material, material_id)

    if not material.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Material not found")

    download_url = None

    if material.file_id and material.file:
        download_url = minio_service.presigned_url(material.file.object_key)
    elif material.external_url:
        download_url = material.external_url

    read = MaterialRead.model_validate(material)
    return MaterialReadWithUrl(**read.model_dump(), download_url=download_url)


@router.post("/materials/{material_id}/view")
def view_material(
    material_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    material = get_or_404(db, Material, material_id)

    if not material.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Material not found")

    db.add(
        MaterialView(
            material_id=material.id,
            user_id=current_user.id,
        )
    )

    material.view_count += 1
    db.commit()

    return {"ok": True}


@router.get("/materials/{material_id}/download")
def download_material(
    material_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    material = get_or_404(db, Material, material_id)

    if not material.is_published:
        raise HTTPException(status_code=404, detail="Material not found")

    if material.file_id and material.file:
        url = minio_service.presigned_url(material.file.object_key)
        return RedirectResponse(url)

    if material.external_url:
        return RedirectResponse(material.external_url)

    raise HTTPException(status_code=404, detail="Material has no source")


@router.patch("/materials/{material_id}", response_model=MaterialRead)
def update_material(
    material_id: UUID,
    payload: MaterialUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    material = get_or_404(db, Material, material_id)
    data = payload.model_dump(exclude_unset=True)

    if "category_id" in data:
        get_or_404(db, Category, data["category_id"])

    if "file_id" in data and data["file_id"]:
        get_or_404(db, FileModel, data["file_id"])

    if "test_id" in data and data["test_id"]:
        get_or_404(db, Test, data["test_id"])

    if "external_url" in data and data["external_url"] == "":
        data["external_url"] = None

    for key, value in data.items():
        setattr(material, key, value)

    db.flush()

    if bool(material.file_id) == bool(material.external_url):
        raise HTTPException(
            status_code=422,
            detail="Material must have exactly one source: file_id or external_url",
        )

    db.commit()
    db.refresh(material)

    return material


@router.delete("/materials/{material_id}", status_code=204)
def delete_material(
    material_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    material = get_or_404(db, Material, material_id)
    file = material.file

    db.delete(material)
    db.flush()

    if file:
        used = (
            db.query(func.count(Material.id))
            .filter(Material.file_id == file.id)
            .scalar()
            or 0
        )

        if used == 0:
            try:
                minio_service.delete_file(file)
            except Exception:
                pass

            db.delete(file)

    db.commit()

    return None


# ==================== TESTS ====================

@router.post("/tests", response_model=TestRead, status_code=201)
def create_test(
    payload: TestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = Test(
        **payload.model_dump(),
        is_published=False,
        created_by=current_user.id,
    )

    db.add(test)
    db.commit()
    db.refresh(test)

    return test


@router.get("/tests", response_model=Page[TestRead])
def list_tests(
    search: str | None = None,
    include_stats: bool = Query(default=True, description="Включить статистику по вопросам"),
    only_complete: bool = Query(default=False, description="Только полностью готовые тесты"),
    only_passable: bool = Query(default=False, description="Только тесты, которые можно пройти"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Test)

    # Ролевая фильтрация
    if current_user.role not in (UserRole.hr, UserRole.admin):
        query = query.filter(Test.is_published.is_(True))

    # Поиск
    if search:
        query = query.filter(
            or_(
                Test.title.ilike(f"%{search}%"),
                Test.topic.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Test.created_at.desc())
    tests = paginate(query, page, size)

    # Если нужна статистика — обогащаем каждый тест
    if include_stats and tests.get("items"):
        test_ids = [t.id for t in tests["items"]]
        stats = _compute_tests_stats(db, test_ids)

        enriched = []
        for test in tests["items"]:
            test_dict = TestRead.model_validate(test).model_dump()
            test_stats = stats.get(test.id, {})
            test_dict.update(test_stats)
            enriched.append(test_dict)

        # Фильтры по готовности
        if only_complete:
            enriched = [t for t in enriched if t.get("is_complete")]
        if only_passable:
            enriched = [t for t in enriched if t.get("is_passable")]

        tests["items"] = enriched

    return tests


def _compute_tests_stats(db: Session, test_ids: list) -> dict[UUID, dict]:
    """
    Вычисляет статистику по вопросам и ответам для списка тестов.
    Возвращает словарь {test_id: {question_count, ...}}
    """
    if not test_ids:
        return {}

    # Получаем все активные вопросы для указанных тестов
    questions = (
        db.query(TestQuestion)
        .filter(
            TestQuestion.test_id.in_(test_ids),
            TestQuestion.is_active.is_(True)
        )
        .all()
    )

    if not questions:
        # Если вопросов нет — возвращаем нулевую статистику для всех тестов
        return {
            tid: {
                "question_count": 0,
                "questions_with_answers": 0,
                "questions_with_correct_answers": 0,
                "total_answers_count": 0,
                "is_complete": False,
                "is_passable": False,
            }
            for tid in test_ids
        }

    # Получаем все активные ответы для этих вопросов
    question_ids = [q.id for q in questions]
    answers = (
        db.query(TestAnswerOption)
        .filter(
            TestAnswerOption.question_id.in_(question_ids),
            TestAnswerOption.is_active.is_(True)
        )
        .all()
    )

    # Группируем ответы по question_id
    answers_by_question = {}
    for answer in answers:
        if answer.question_id not in answers_by_question:
            answers_by_question[answer.question_id] = []
        answers_by_question[answer.question_id].append(answer)

    # Считаем статистику для каждого теста
    stats = {}
    questions_by_test = {}

    for question in questions:
        if question.test_id not in questions_by_test:
            questions_by_test[question.test_id] = []
        questions_by_test[question.test_id].append(question)

    for test_id in test_ids:
        test_questions = questions_by_test.get(test_id, [])
        q_count = len(test_questions)
        
        with_answers = 0
        with_correct = 0
        total_answers = 0

        for question in test_questions:
            q_answers = answers_by_question.get(question.id, [])
            answer_count = len(q_answers)
            
            if answer_count > 0:
                with_answers += 1
                total_answers += answer_count
                
                # Проверяем, есть ли правильный ответ (score > 0)
                if any(a.score > 0 for a in q_answers):
                    with_correct += 1

        stats[test_id] = {
            "question_count": q_count,
            "questions_with_answers": with_answers,
            "questions_with_correct_answers": with_correct,
            "total_answers_count": total_answers,
            "is_complete": q_count > 0 and q_count == with_answers,
            "is_passable": with_correct > 0,
        }

    return stats


@router.get("/tests/{test_id}/full", response_model=TestFullRead)
def get_test_full(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    return get_or_404(db, Test, test_id)


@router.get("/tests/{test_id}", response_model=TestRead)
def get_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    test = get_or_404(db, Test, test_id)

    if not test.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Test not found")

    return test


@router.patch("/tests/{test_id}", response_model=TestRead)
def update_test(
    test_id: UUID,
    payload: TestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)
    data = payload.model_dump(exclude_unset=True)

    try:
        for key, value in data.items():
            setattr(test, key, value)

        db.flush()
        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            test_service.validate_publish(db, test)

        db.commit()
        db.refresh(test)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict")

    return test


@router.post("/tests/{test_id}/publish", response_model=TestRead)
def publish_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)

    try:
        test.is_published = True
        db.flush()

        test_service.validate_publish(db, test)

        db.commit()
        db.refresh(test)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict")

    return test


@router.post("/tests/{test_id}/unpublish", response_model=TestRead)
def unpublish_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)
    test.is_published = False

    db.commit()
    db.refresh(test)

    return test


@router.post("/tests/{test_id}/recalculate", response_model=TestRead)
def recalculate_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)

    test_service.recalculate_test_scores(db, test)
    db.commit()
    db.refresh(test)

    return test


@router.delete("/tests/{test_id}", status_code=204)
def delete_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)

    try:
        db.delete(test)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Test cannot be deleted because it has attempts or references",
        )

    return None


# ==================== QUESTIONS ====================

@router.post("/tests/{test_id}/questions", response_model=QuestionRead, status_code=201)
def create_question(
    test_id: UUID,
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)

    try:
        question = TestQuestion(
            test_id=test.id,
            text=payload.text,
            question_type=payload.question_type,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )

        db.add(question)
        db.flush()

        for answer in payload.answers:
            db.add(
                TestAnswerOption(
                    question_id=question.id,
                    **answer.model_dump(),
                )
            )

        db.flush()

        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            test_service.validate_publish(db, test)

        db.commit()
        db.refresh(question)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict")

    return question


@router.get("/tests/{test_id}/questions", response_model=list[QuestionRead])
def list_questions(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    test = get_or_404(db, Test, test_id)

    return (
        db.query(TestQuestion)
        .filter(TestQuestion.test_id == test.id)
        .order_by(TestQuestion.sort_order)
        .all()
    )


@router.patch("/questions/{question_id}", response_model=QuestionRead)
def update_question(
    question_id: UUID,
    payload: QuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    question = get_or_404(db, TestQuestion, question_id)
    test = question.test

    try:
        data = payload.model_dump(exclude_unset=True)

        for key, value in data.items():
            setattr(question, key, value)

        db.flush()

        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            test_service.validate_publish(db, test)

        db.commit()
        db.refresh(question)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict")

    return question


from fastapi import Response

@router.delete(
    "/questions/{question_id}",
    responses={
        200: {
            "model": QuestionRead,
            "description": "Вопрос деактивирован вместо удаления (используется в попытках)",
        },
        204: {"description": "Вопрос полностью удалён"},
    },
)
def delete_question(
    question_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    question = get_or_404(db, TestQuestion, question_id)
    test = question.test

    # Проверяем, использовался ли вопрос в попытках
    attempt_answers_count = (
        db.query(func.count(TestAttemptAnswer.id))
        .filter(TestAttemptAnswer.question_id == question_id)
        .scalar()
        or 0
    )

    try:
        if attempt_answers_count > 0:
            # === Вопрос используется в попытках — делаем неактивным ===
            if question.is_active:
                question.is_active = False
                db.flush()

                # Пересчитываем баллы теста
                test_service.recalculate_test_scores(db, test)

                # Проверяем валидность публикации
                if test.is_published:
                    try:
                        test_service.validate_publish(db, test)
                    except HTTPException:
                        # Если тест стал невалидным — снимаем с публикации
                        test.is_published = False

                db.commit()
                db.refresh(question)

            # Возвращаем обновлённый вопрос (статус 200)
            return question

        # === Вопрос не используется — удаляем полностью ===
        # Удаляем все варианты ответов
        db.query(TestAnswerOption).filter(
            TestAnswerOption.question_id == question_id
        ).delete(synchronize_session=False)

        # Удаляем сам вопрос
        db.delete(question)
        db.flush()

        # Пересчитываем баллы теста
        test_service.recalculate_test_scores(db, test)

        # Проверяем валидность публикации
        if test.is_published:
            try:
                test_service.validate_publish(db, test)
            except HTTPException:
                test.is_published = False

        db.commit()

        # Возвращаем 204 (успешное удаление без тела)
        return Response(status_code=204)

    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Не удалось удалить вопрос из-за связанных данных",
        )

# ==================== ANSWERS ====================

@router.post("/questions/{question_id}/answers", response_model=AnswerOptionRead, status_code=201)
def create_answer(
    question_id: UUID,
    payload: AnswerOptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    question = get_or_404(db, TestQuestion, question_id)
    test = question.test

    try:
        # === IDEMPOTENCY: проверяем, нет ли уже ответа с таким текстом ===
        existing = (
            db.query(TestAnswerOption)
            .filter(
                TestAnswerOption.question_id == question_id,
                TestAnswerOption.text == payload.text,
            )
            .first()
        )

        if existing:
            # Обновляем существующий вместо создания дубликата
            existing.score = payload.score
            existing.sort_order = payload.sort_order
            existing.is_active = payload.is_active
            db.flush()

            test_service.recalculate_test_scores(db, test)

            if test.is_published:
                test_service.validate_publish(db, test)

            db.commit()
            db.refresh(existing)
            return existing

        # === Создаём новый ответ ===
        answer = TestAnswerOption(
            question_id=question.id,
            **payload.model_dump(),
        )

        db.add(answer)
        db.flush()

        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            test_service.validate_publish(db, test)

        db.commit()
        db.refresh(answer)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict")

    return answer

    
@router.patch("/answers/{answer_id}", response_model=AnswerOptionRead)
def update_answer(
    answer_id: UUID,
    payload: AnswerOptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    answer = get_or_404(db, TestAnswerOption, answer_id)
    question = answer.question
    test = question.test

    try:
        data = payload.model_dump(exclude_unset=True)

        for key, value in data.items():
            setattr(answer, key, value)

        db.flush()

        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            test_service.validate_publish(db, test)

        db.commit()
        db.refresh(answer)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict")

    return answer


from sqlalchemy import cast, Text

@router.delete("/answers/{answer_id}", status_code=204)
def delete_answer(
    answer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    answer = db.query(TestAnswerOption).filter(
        TestAnswerOption.id == answer_id
    ).first()

    # === IDEMPOTENCY: если ответа нет — всё равно успех ===
    if not answer:
        return None

    question = answer.question
    test = question.test

    # Проверяем, использовался ли ответ в попытках
    # Приводим JSON к тексту, чтобы работал LIKE
    used_in_attempts = (
        db.query(func.count(TestAttemptAnswer.id))
        .join(TestAttempt, TestAttemptAnswer.attempt_id == TestAttempt.id)
        .filter(
            TestAttempt.test_id == test.id,
            cast(TestAttemptAnswer.selected_option_ids, Text).contains(str(answer_id))
        )
        .scalar()
        or 0
    )

    try:
        if used_in_attempts > 0:
            # Если ответ использовался — делаем неактивным вместо удаления
            answer.is_active = False
        else:
            db.delete(answer)
        
        db.flush()

        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            try:
                test_service.validate_publish(db, test)
            except HTTPException:
                test.is_published = False

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict")

    return None
    

# ==================== GRADES ====================

@router.post("/tests/{test_id}/grades", response_model=GradeRead, status_code=201)
def create_grade(
    test_id: UUID,
    payload: GradeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    get_or_404(db, Test, test_id)

    test_service.assert_grade_no_overlap(
        db,
        test_id,
        payload.min_score,
        payload.max_score,
    )

    grade = TestGrade(
        test_id=test_id,
        **payload.model_dump(),
    )

    db.add(grade)
    db.commit()
    db.refresh(grade)

    return grade


@router.delete("/grades/{grade_id}", status_code=204)
def delete_grade(
    grade_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    grade = get_or_404(db, TestGrade, grade_id)

    db.delete(grade)
    db.commit()  # Важно: commit сразу после удаления

    return None

@router.get("/tests/{test_id}/grades", response_model=list[GradeRead])
def list_grades(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    test = get_or_404(db, Test, test_id)

    if not test.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Test not found")

    return (
        db.query(TestGrade)
        .filter(TestGrade.test_id == test.id)
        .order_by(TestGrade.sort_order, TestGrade.min_score)
        .all()
    )


@router.patch("/grades/{grade_id}", response_model=GradeRead)
def update_grade(
    grade_id: UUID,
    payload: GradeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    grade = get_or_404(db, TestGrade, grade_id)
    data = payload.model_dump(exclude_unset=True)

    min_score = data.get("min_score", grade.min_score)
    max_score = data.get("max_score", grade.max_score)

    if max_score is not None and max_score < min_score:
        raise HTTPException(status_code=422, detail="max_score must be >= min_score")

    test_service.assert_grade_no_overlap(
        db,
        grade.test_id,
        min_score,
        max_score,
        exclude_id=grade.id,
    )

    for key, value in data.items():
        setattr(grade, key, value)

    db.commit()
    db.refresh(grade)

    return grade


# ==================== ATTEMPTS ====================

@router.get("/tests/{test_id}/access", response_model=AttemptAccess)
def test_access(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    test = get_or_404(db, Test, test_id)

    if not test.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Test not found")

    return test_service.get_attempt_access(db, test, current_user)


@router.get("/attempts/{attempt_id}/detail", response_model=AttemptDetailRead)
def get_attempt_detail(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Полная деталь попытки с вопросами и вариантами ответов"""
    attempt = get_or_404(db, TestAttempt, attempt_id)

    # Проверка прав: только владелец, HR или админ
    if current_user.id != attempt.user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Получаем связанные данные
    test = db.query(Test).filter(Test.id == attempt.test_id).first()
    user = db.query(User).filter(User.id == attempt.user_id).first()

    # Получаем ответы пользователя
    attempt_answers = (
        db.query(TestAttemptAnswer)
        .filter(TestAttemptAnswer.attempt_id == attempt_id)
        .all()
    )

    # Собираем детали по вопросам
    questions_detail = []
    
    for attempt_answer in attempt_answers:
        # Получаем вопрос
        question = db.query(TestQuestion).filter(
            TestQuestion.id == attempt_answer.question_id
        ).first()
        
        if not question:
            continue

        # Получаем все варианты ответов для вопроса
        options = (
            db.query(TestAnswerOption)
            .filter(
                TestAnswerOption.question_id == question.id,
                TestAnswerOption.is_active.is_(True)
            )
            .order_by(TestAnswerOption.sort_order)
            .all()
        )

        # ID выбранных пользователем вариантов
        selected_ids = set(attempt_answer.selected_option_ids or [])

        # Формируем детали вариантов
        options_detail = []
        for option in options:
            is_selected = str(option.id) in selected_ids or option.id in selected_ids
            is_correct = option.score > 0
            
            options_detail.append(AttemptAnswerOptionDetail(
                id=option.id,
                text=option.text,
                score=option.score,
                is_selected=is_selected,
                is_correct=is_correct,
            ))

        # Определяем правильность ответа пользователя
        # Правильно если все выбранные варианты правильные и набран полный балл
        is_correct_answer = attempt_answer.score >= attempt_answer.max_score and attempt_answer.max_score > 0

        questions_detail.append(AttemptQuestionDetail(
            question_id=question.id,
            question_text=question.text,
            question_type=question.question_type.value,
            user_score=attempt_answer.score,
            max_score=attempt_answer.max_score,
            is_correct=is_correct_answer,
            options=options_detail,
        ))


    return AttemptDetailRead(
        id=attempt.id,
        test_id=attempt.test_id,
        test_title=test.title if test else None,
        user_id=attempt.user_id,
        user_name=user.full_name if user else None,
        attempt_number=attempt.attempt_number,
        status=attempt.status.value,
        score=attempt.score,
        max_score=attempt.max_score,
        passing_score=attempt.passing_score,
        passed=attempt.passed,
        grade_name=attempt.grade_name,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        questions=questions_detail,
    )

@router.post("/tests/{test_id}/attempts", response_model=AttemptStartRead, status_code=201)
def start_attempt(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    test = get_or_404(db, Test, test_id)

    if not test.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=404, detail="Test not found")

    access = test_service.get_attempt_access(db, test, current_user)

    if not access["can_start"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    attempt = TestAttempt(
        test_id=test.id,
        user_id=current_user.id,
        status=AttemptStatus.in_progress,
        attempt_number=access["completed_attempts"] + 1,
        max_score=test.max_score,
        passing_score=test.passing_score,
    )

    db.add(attempt)
    db.flush()

    questions = [q for q in test.questions if q.is_active]

    if test.shuffle_questions:
        random.shuffle(questions)

    public_questions = []

    for question in questions:
        answers = [a for a in question.answers if a.is_active]

        if test.shuffle_questions:
            random.shuffle(answers)

        public_questions.append(
            QuestionPublic(
                id=question.id,
                text=question.text,
                question_type=question.question_type,
                answers=[
                    AnswerOptionPublic(id=a.id, text=a.text)
                    for a in answers
                ],
            )
        )

    db.commit()

    return AttemptStartRead(
        id=attempt.id,
        test_id=attempt.test_id,
        attempt_number=attempt.attempt_number,
        max_score=attempt.max_score,
        passing_score=attempt.passing_score,
        questions=public_questions,
    )

@router.get("/tests/{test_id}/attempts", response_model=Page[AttemptRead])
def list_test_attempts(
    test_id: UUID,
    status: str | None = None,
    passed: str | None = None,
    user_search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location_type: str | None = None,
    location_city: str | None = None,
    location_id: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    from app.models import Location
    
    get_or_404(db, Test, test_id)

    query = (
        db.query(TestAttempt)
        .join(User, TestAttempt.user_id == User.id)
        .outerjoin(Location, User.location_id == Location.id)
        .filter(TestAttempt.test_id == test_id)
    )

    # Фильтры
    if status:
        query = query.filter(TestAttempt.status == status)
    
    if passed == "passed":
        query = query.filter(TestAttempt.passed == True)
    elif passed == "failed":
        query = query.filter(TestAttempt.passed == False)
    
    if user_search:
        query = query.filter(
            or_(
                User.full_name.ilike(f"%{user_search}%"),
                User.id_max.ilike(f"%{user_search}%"),
            )
        )
    
    if date_from:
        try:
            from datetime import datetime
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(TestAttempt.started_at >= dt_from)
        except ValueError:
            pass
    
    if date_to:
        try:
            from datetime import datetime, timedelta
            dt_to = datetime.fromisoformat(date_to) + timedelta(days=1)
            query = query.filter(TestAttempt.started_at < dt_to)
        except ValueError:
            pass
    
    if location_type:
        query = query.filter(Location.location_type == location_type)
    
    if location_city:
        query = query.filter(Location.city == location_city)
    
    if location_id:
        query = query.filter(User.location_id == location_id)

    query = query.order_by(TestAttempt.started_at.desc())
    
    # Получаем результаты
    total = query.count()
    attempts = query.offset((page - 1) * size).limit(size).all()
    
    # Обогащаем данными о подразделении
    enriched = []
    for attempt in attempts:
        attempt_dict = AttemptRead.model_validate(attempt).model_dump()
        
        # Добавляем информацию о пользователе и подразделении
        user = attempt.user
        location = user.location if hasattr(user, 'location') else None
        
        attempt_dict["user_name"] = user.full_name
        attempt_dict["user_email"] = getattr(user, 'email', None)
        attempt_dict["user_id_max"] = user.id_max
        
        if location:
            attempt_dict["location_id"] = str(location.id)
            attempt_dict["location_name"] = location.name
            attempt_dict["location_city"] = location.city
            attempt_dict["location_address"] = location.address
            attempt_dict["location_type"] = location.location_type.value if location.location_type else None
        else:
            attempt_dict["location_id"] = None
            attempt_dict["location_name"] = None
            attempt_dict["location_city"] = None
            attempt_dict["location_address"] = None
            attempt_dict["location_type"] = None
        
        enriched.append(attempt_dict)
    
    return {
        "items": enriched,
        "total": total,
        "page": page,
        "size": size,
    }

@router.get("/tests/{test_id}/attempts/filters")
def get_attempt_filters(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    """Возвращает доступные фильтры для попыток теста"""
    from app.models import Location
    
    get_or_404(db, Test, test_id)
    
    # Получаем все попытки теста с пользователями и подразделениями
    attempts = (
        db.query(TestAttempt)
        .join(User, TestAttempt.user_id == User.id)
        .outerjoin(Location, User.location_id == Location.id)
        .filter(TestAttempt.test_id == test_id)
        .all()
    )
    
    # Собираем уникальные города
    cities = sorted(set(
        attempt.user.location.city 
        for attempt in attempts 
        if attempt.user.location and attempt.user.location.city
    ))
    
    # Собираем уникальные подразделения
    locations = {}
    for attempt in attempts:
        if attempt.user.location:
            loc = attempt.user.location
            locations[str(loc.id)] = {
                "id": str(loc.id),
                "name": loc.name,
                "city": loc.city,
                "type": loc.location_type.value if loc.location_type else None
            }
    
    return {
        "cities": cities,
        "locations": list(locations.values()),
        "location_types": ["office", "warehouse", "store"]
    }
    

@router.get("/attempts/{attempt_id}", response_model=AttemptRead)
def get_attempt(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = get_or_404(db, TestAttempt, attempt_id)

    if current_user.id != attempt.user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    return attempt


@router.post("/attempts/{attempt_id}/complete", response_model=AttemptRead)
def complete_attempt(
    attempt_id: UUID,
    payload: AttemptSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = get_or_404(db, TestAttempt, attempt_id)

    if current_user.id != attempt.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return test_service.complete_attempt(db, attempt, payload)


@router.post("/attempts/{attempt_id}/cancel", response_model=AttemptRead)
def cancel_attempt(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attempt = get_or_404(db, TestAttempt, attempt_id)

    if current_user.id != attempt.user_id and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    if attempt.status != AttemptStatus.in_progress:
        raise HTTPException(status_code=409, detail="Attempt is not in progress")

    attempt.status = AttemptStatus.canceled
    db.commit()
    db.refresh(attempt)

    return attempt


@router.get("/me/attempts", response_model=Page[AttemptRead])
def my_attempts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(TestAttempt)
        .filter(TestAttempt.user_id == current_user.id)
        .order_by(TestAttempt.started_at.desc())
    )

    return paginate(query, page, size)

# ==================== LOCATIONS ====================

@router.get("/locations", response_model=list[LocationRead])
def list_locations(
    location_type: str | None = Query(default=None, description="Фильтр по типу"),
    city: str | None = Query(default=None, description="Фильтр по городу"),
    is_active: bool | None = Query(default=None, description="Фильтр по статусу"),
    search: str | None = Query(default=None, description="Поиск по названию или адресу"),
    include_inactive: bool = Query(default=True, description="Включая неактивные"),
    db: Session = Depends(get_db),
):
    """Список подразделений с фильтрами"""
    query = db.query(Location)

    if not include_inactive and is_active is None:
        query = query.filter(Location.is_active.is_(True))
    elif is_active is not None:
        query = query.filter(Location.is_active == is_active)

    if location_type:
        query = query.filter(Location.location_type == location_type)

    if city:
        query = query.filter(Location.city == city)

    if search:
        query = query.filter(
            or_(
                Location.name.ilike(f"%{search}%"),
                Location.address.ilike(f"%{search}%"),
                Location.city.ilike(f"%{search}%"),
            )
        )

    return query.order_by(Location.sort_order, Location.city, Location.name).all()

@router.get("/locations/types", response_model=list[str])
def list_location_types(db: Session = Depends(get_db)):
    """Доступные типы подразделений с количеством активных."""
    types = [
        {"value": "office", "label": "Офис"},
        {"value": "warehouse", "label": "Склад"},
        {"value": "store", "label": "Магазин"},
    ]
    return types


@router.get("/locations/cities", response_model=list[str])
def list_location_cities(
    location_type: str = Query(..., description="Тип подразделения"),
    db: Session = Depends(get_db),
):
    """Список городов для выбранного типа подразделения."""
    cities = (
        db.query(Location.city)
        .filter(
            Location.location_type == location_type,
            Location.is_active.is_(True),
        )
        .distinct()
        .order_by(Location.city)
        .all()
    )
    return [c[0] for c in cities]


@router.post("/locations", response_model=LocationRead, status_code=201)
def create_location(
    payload: LocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    location = Location(**payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.patch("/locations/{location_id}", response_model=LocationRead)
def update_location(
    location_id: UUID,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    location = get_or_404(db, Location, location_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(location, key, value)
    db.commit()
    db.refresh(location)
    return location


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(
    location_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    location = get_or_404(db, Location, location_id)
    db.delete(location)
    db.commit()
    return None