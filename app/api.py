import random
from uuid import UUID

from fastapi import APIRouter, Depends, File as FileField, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, text
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
    CategoryContents,
    CategoryCreate,
    CategoryRead,
    CategoryTree,
    CategoryUpdate,
    FileRead,
    GradeCreate,
    GradeRead,
    GradeUpdate,
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

    if not material.is_published and current_user.role not in (
        UserRole.hr,
        UserRole.admin,
    ):
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
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Test)

    if current_user.role not in (UserRole.hr, UserRole.admin):
        query = query.filter(Test.is_published.is_(True))

    if search:
        query = query.filter(
            or_(
                Test.title.ilike(f"%{search}%"),
                Test.topic.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Test.created_at.desc())
    return paginate(query, page, size)


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


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(
    question_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    question = get_or_404(db, TestQuestion, question_id)
    test = question.test

    try:
        db.delete(question)
        db.flush()

        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            test_service.validate_publish(db, test)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Question cannot be deleted because it has attempt answers",
        )

    return None


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


@router.delete("/answers/{answer_id}", status_code=204)
def delete_answer(
    answer_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    answer = get_or_404(db, TestAnswerOption, answer_id)
    question = answer.question
    test = question.test

    try:
        db.delete(answer)
        db.flush()

        test_service.recalculate_test_scores(db, test)

        if test.is_published:
            test_service.validate_publish(db, test)

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
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(HRRequired),
):
    get_or_404(db, Test, test_id)

    query = (
        db.query(TestAttempt)
        .filter(TestAttempt.test_id == test_id)
        .order_by(TestAttempt.started_at.desc())
    )

    return paginate(query, page, size)


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