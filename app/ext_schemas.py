from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ext_models import AssignmentStatus
from app.schemas import (
    AttemptRead,
    MaterialSummary,
    TestRead,
    TestSummary,
    UserRead,
)



# ==================== ANALYTICS ====================

class AnalyticsSummary(BaseModel):
    users_total: int = Field(description="Общее количество пользователей")
    active_users: int = Field(description="Количество активных пользователей")

    materials_total: int = Field(description="Общее количество материалов")
    published_materials: int = Field(description="Количество опубликованных материалов")

    categories_total: int = Field(description="Количество категорий")

    tests_total: int = Field(description="Общее количество тестов")
    published_tests: int = Field(description="Количество опубликованных тестов")

    attempts_total: int = Field(description="Общее количество попыток")
    completed_attempts: int = Field(description="Количество завершённых попыток")
    passed_attempts: int = Field(description="Количество пройденных попыток")
    failed_attempts: int = Field(description="Количество не пройденных попыток")

    views_total: int = Field(description="Суммарное количество просмотров материалов")
    files_total: int = Field(description="Количество загруженных файлов")

    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл по завершённым попыткам",
    )
    avg_percent: Optional[float] = Field(
        default=None,
        description="Средний процент результата по завершённым попыткам",
    )
    pass_rate: Optional[float] = Field(
        default=None,
        description="Процент прохождения среди завершённых попыток",
    )

    assignments_total: int = Field(description="Общее количество назначений")
    completed_assignments: int = Field(description="Количество завершённых назначений")
    overdue_assignments: int = Field(description="Количество просроченных назначений")

    avg_material_rating: Optional[float] = Field(
        default=None,
        description="Средний рейтинг по всем отзывам на материалы",
    )


class AttemptsByDay(BaseModel):
    day: date = Field(description="Дата")
    attempts: int = Field(description="Количество попыток")
    passed: int = Field(description="Количество пройденных попыток")
    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл за день",
    )


class ViewsByDay(BaseModel):
    day: date = Field(description="Дата")
    views: int = Field(description="Количество просмотров")


class TestAnalytics(BaseModel):
    test_id: UUID = Field(description="Идентификатор теста")
    title: str = Field(description="Название теста")
    attempts: int = Field(description="Количество завершённых попыток")
    passed: int = Field(description="Количество пройденных попыток")
    pass_rate: float = Field(description="Процент прохождения")
    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл по тесту",
    )


class MaterialAnalytics(BaseModel):
    material_id: UUID = Field(description="Идентификатор материала")
    title: str = Field(description="Название материала")
    views: int = Field(description="Количество просмотров")
    avg_rating: Optional[float] = Field(
        default=None,
        description="Средний рейтинг материала",
    )
    feedback_count: int = Field(description="Количество отзывов")


class UserAnalytics(BaseModel):
    user_id: UUID = Field(description="Идентификатор пользователя")
    full_name: str = Field(description="ФИО пользователя")
    attempts: int = Field(description="Количество завершённых попыток")
    passed: int = Field(description="Количество пройденных попыток")
    pass_rate: float = Field(description="Процент прохождения")
    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл пользователя",
    )
    views: int = Field(description="Количество просмотров материалов")


class QuestionDifficulty(BaseModel):
    question_id: UUID = Field(description="Идентификатор вопроса")
    text: str = Field(description="Текст вопроса")
    test_title: str = Field(description="Название теста")
    answers_count: int = Field(description="Сколько раз отвечали на вопрос")
    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл по вопросу",
    )
    avg_percent: Optional[float] = Field(
        default=None,
        description="Средний процент результата по вопросу",
    )
    zero_rate: Optional[float] = Field(
        default=None,
        description="Процент ответов с нулевым баллом",
    )


class CategoryAnalytics(BaseModel):
    category_id: UUID = Field(description="Идентификатор категории")
    name: str = Field(description="Название категории")
    materials: int = Field(description="Количество материалов в категории")
    views: int = Field(description="Суммарные просмотры материалов категории")


class GradeDistribution(BaseModel):
    grade_name: str = Field(description="Название градации")
    count: int = Field(description="Количество попыток с этой градацией")


class TestDetailAnalytics(BaseModel):
    test: TestRead = Field(description="Данные теста")
    attempts_total: int = Field(description="Все попытки по тесту")
    completed_attempts: int = Field(description="Завершённые попытки")
    passed_attempts: int = Field(description="Пройденные попытки")
    pass_rate: Optional[float] = Field(
        default=None,
        description="Процент прохождения",
    )
    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл",
    )
    attempts_by_day: List[AttemptsByDay] = Field(
        description="Попытки по дням",
    )
    grade_distribution: List[GradeDistribution] = Field(
        description="Распределение градаций",
    )


class MaterialDetailAnalytics(BaseModel):
    material: MaterialSummary = Field(description="Данные материала")
    views_total: int = Field(description="Всего просмотров")
    unique_viewers: int = Field(description="Сколько уникальных пользователей смотрели материал")
    avg_rating: Optional[float] = Field(
        default=None,
        description="Средний рейтинг",
    )
    feedback_count: int = Field(description="Количество отзывов")
    views_by_day: List[ViewsByDay] = Field(
        description="Просмотры по дням",
    )


class UserDetailsAnalytics(BaseModel):
    user: UserRead = Field(description="Данные пользователя")
    attempts_total: int = Field(description="Все попытки пользователя")
    completed_attempts: int = Field(description="Завершённые попытки")
    passed_attempts: int = Field(description="Пройденные попытки")
    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл",
    )
    views_total: int = Field(description="Количество просмотров материалов")
    assignments_total: int = Field(description="Всего назначений")
    completed_assignments: int = Field(description="Завершённые назначения")
    overdue_assignments: int = Field(description="Просроченные назначения")
    last_attempts: List[AttemptRead] = Field(
        default_factory=list,
        description="Последние попытки пользователя",
    )


class AnalyticsDashboard(BaseModel):
    summary: AnalyticsSummary = Field(description="Общая сводка")
    attempts_by_day: List[AttemptsByDay] = Field(description="Попытки по дням")
    views_by_day: List[ViewsByDay] = Field(description="Просмотры по дням")
    top_tests: List[TestAnalytics] = Field(description="Топ тестов")
    top_materials: List[MaterialAnalytics] = Field(description="Топ материалов")
    top_users: List[UserAnalytics] = Field(description="Топ пользователей")


# ==================== ASSIGNMENTS ====================

class AssignmentCreate(BaseModel):
    user_id: UUID = Field(description="Кому назначаем")
    material_id: Optional[UUID] = Field(
        default=None,
        description="Материал для назначения",
    )
    test_id: Optional[UUID] = Field(
        default=None,
        description="Тест для назначения",
    )
    due_date: Optional[datetime] = Field(
        default=None,
        description="Срок выполнения",
    )
    note: Optional[str] = Field(
        default=None,
        description="Комментарий к назначению",
    )

    @model_validator(mode="after")
    def validate_object(self):
        if bool(self.material_id) == bool(self.test_id):
            raise ValueError(
                "Нужно указать ровно один объект: material_id или test_id"
            )
        return self


class AssignmentBulkCreate(BaseModel):
    user_ids: List[UUID] = Field(
        min_length=1,
        description="Список пользователей, которым назначаем",
    )
    material_id: Optional[UUID] = Field(
        default=None,
        description="Материал для назначения",
    )
    test_id: Optional[UUID] = Field(
        default=None,
        description="Тест для назначения",
    )
    due_date: Optional[datetime] = Field(
        default=None,
        description="Срок выполнения",
    )
    note: Optional[str] = Field(
        default=None,
        description="Комментарий к назначению",
    )

    @model_validator(mode="after")
    def validate_object(self):
        if bool(self.material_id) == bool(self.test_id):
            raise ValueError(
                "Нужно указать ровно один объект: material_id или test_id"
            )
        return self


class AssignmentUpdate(BaseModel):
    status: Optional[AssignmentStatus] = Field(
        default=None,
        description="Статус назначения",
    )
    due_date: Optional[datetime] = Field(
        default=None,
        description="Срок выполнения",
    )
    note: Optional[str] = Field(
        default=None,
        description="Комментарий",
    )


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Идентификатор назначения")
    user_id: UUID = Field(description="Пользователь")
    material_id: Optional[UUID] = Field(
        default=None,
        description="Материал",
    )
    test_id: Optional[UUID] = Field(
        default=None,
        description="Тест",
    )
    assigned_by: Optional[UUID] = Field(
        default=None,
        description="Кто назначил",
    )
    status: AssignmentStatus = Field(description="Статус")
    due_date: Optional[datetime] = Field(
        default=None,
        description="Срок выполнения",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Когда завершено",
    )
    note: Optional[str] = Field(
        default=None,
        description="Комментарий",
    )
    created_at: datetime = Field(description="Дата создания")

    user: Optional[UserRead] = Field(
        default=None,
        description="Данные пользователя",
    )
    material: Optional[MaterialSummary] = Field(
        default=None,
        description="Данные материала",
    )
    test: Optional[TestSummary] = Field(
        default=None,
        description="Данные теста",
    )


class AssignmentBulkResult(BaseModel):
    created: int = Field(description="Сколько назначений создано")


# ==================== FEEDBACK ====================

class FeedbackCreate(BaseModel):
    rating: int = Field(
        ge=1,
        le=5,
        description="Оценка от 1 до 5",
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Комментарий к материалу",
    )


class FeedbackUpdate(BaseModel):
    rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Оценка от 1 до 5",
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Комментарий к материалу",
    )


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Идентификатор отзыва")
    material_id: UUID = Field(description="Материал")
    user_id: UUID = Field(description="Автор отзыва")
    rating: int = Field(description="Оценка")
    comment: Optional[str] = Field(
        default=None,
        description="Комментарий",
    )
    created_at: datetime = Field(description="Дата создания")


class MaterialRatingRead(BaseModel):
    material_id: UUID = Field(description="Материал")
    avg_rating: Optional[float] = Field(
        default=None,
        description="Средний рейтинг",
    )
    feedback_count: int = Field(description="Количество отзывов")


# ==================== MY DASHBOARD ====================

class MyDashboard(BaseModel):
    completed_attempts: int = Field(description="Завершённые попытки")
    passed_attempts: int = Field(description="Пройденные попытки")
    failed_attempts: int = Field(description="Не пройденные попытки")
    avg_score: Optional[float] = Field(
        default=None,
        description="Средний балл",
    )
    views_total: int = Field(description="Сколько материалов просмотрено")
    assignments_total: int = Field(description="Всего назначений")
    assignments_completed: int = Field(description="Завершённые назначения")
    assignments_in_progress: int = Field(description="Назначения в работе")
    assignments_overdue: int = Field(description="Просроченные назначения")
    feedback_count: int = Field(description="Сколько отзывов оставлено")


class AssignmentDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    user_name: str | None
    user_id_max: str | None
    material_id: UUID | None
    test_id: UUID | None
    status: AssignmentStatus
    due_date: datetime | None
    note: str | None
    created_at: datetime
    completed_at: datetime | None
    
    # Детальная информация
    material_viewed: bool
    material_viewed_at: datetime | None
    test_passed: bool
    test_passed_at: datetime | None
    test_score: int | None
    test_max_score: int | None
    test_grade: str | None