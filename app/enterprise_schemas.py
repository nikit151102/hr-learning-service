from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enterprise_models import CourseEnrollmentStatus, NotificationType
from app.schemas import UserRead


# ==================== MANAGERS / DEPARTMENTS / MANDATORY ====================

class ManagerRightCreate(BaseModel):
    user_id: UUID = Field(description="Пользователь, которому даём права руководителя")
    department: Optional[str] = Field(
        default=None,
        description="Отдел. Если пусто, руководитель видит все отделы.",
    )


class ManagerRightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    department: Optional[str]
    created_at: datetime


class EmployeeDepartmentSet(BaseModel):
    user_id: UUID = Field(description="Пользователь")
    department: str = Field(description="Отдел сотрудника")


class EmployeeDepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    department: str


class MandatoryTestCreate(BaseModel):
    test_id: UUID = Field(description="Тест, который становится обязательным")


class MandatoryTestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    test_id: UUID
    created_at: datetime


# ==================== COURSES ====================

class CourseCreate(BaseModel):
    title: str = Field(description="Название курса")
    description: Optional[str] = Field(default=None, description="Описание курса")
    is_published: bool = Field(default=False, description="Опубликован ли курс")
    is_mandatory: bool = Field(default=False, description="Обязательный ли курс")


class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_published: Optional[bool] = None
    is_mandatory: Optional[bool] = None


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str]
    is_published: bool
    is_mandatory: bool
    created_at: datetime


class CourseItemCreate(BaseModel):
    material_id: Optional[UUID] = Field(default=None, description="Материал курса")
    test_id: Optional[UUID] = Field(default=None, description="Тест курса")
    sort_order: int = Field(default=0, description="Порядковый номер")
    is_required: bool = Field(default=True, description="Обязательный ли элемент курса")

    @model_validator(mode="after")
    def validate_object(self):
        if bool(self.material_id) == bool(self.test_id):
            raise ValueError("Нужно указать ровно один объект: material_id или test_id")
        return self


class CourseItemUpdate(BaseModel):
    material_id: Optional[UUID] = None
    test_id: Optional[UUID] = None
    sort_order: Optional[int] = None
    is_required: Optional[bool] = None


class CourseItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    material_id: Optional[UUID]
    test_id: Optional[UUID]
    sort_order: int
    is_required: bool


class CourseEnrollmentCreate(BaseModel):
    user_ids: List[UUID] = Field(min_length=1, description="Список пользователей")
    due_date: Optional[datetime] = Field(default=None, description="Срок прохождения")
    note: Optional[str] = Field(default=None, description="Комментарий")


class CourseEnrollmentBulkResult(BaseModel):
    created: int = Field(description="Сколько записей создано")
    updated: int = Field(description="Сколько записей обновлено")


class CourseEnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    user_id: UUID
    assigned_by: Optional[UUID]
    status: CourseEnrollmentStatus
    due_date: Optional[datetime]
    progress_percent: int
    completed_at: Optional[datetime]
    note: Optional[str]
    created_at: datetime

    user: Optional[UserRead] = None
    course: Optional[CourseRead] = None


class CourseEnrollmentProgressItem(BaseModel):
    item_id: UUID
    object_type: str
    object_id: Optional[UUID]
    object_title: Optional[str]
    is_required: bool
    completed: bool


class CourseEnrollmentProgressRead(BaseModel):
    enrollment: CourseEnrollmentRead
    items: List[CourseEnrollmentProgressItem]


# ==================== CERTIFICATES ====================

class CertificateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    certificate_number: str
    user_id: UUID
    course_id: Optional[UUID]
    test_id: Optional[UUID]
    issued_at: datetime
    revoked_at: Optional[datetime]


class CertificateVerify(BaseModel):
    valid: bool = Field(description="Действителен ли сертификат")
    certificate_number: str
    issued_at: datetime
    revoked_at: Optional[datetime]
    owner_full_name: str
    object_type: str
    object_title: str


# ==================== NOTIFICATIONS ====================

class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: NotificationType
    title: str
    message: str
    entity_type: Optional[str]
    entity_id: Optional[UUID]
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime]


class UnreadNotificationsCount(BaseModel):
    unread: int


# ==================== AUDIT ====================

class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID]
    method: str
    path: str
    action: str
    entity_type: Optional[str]
    entity_id: Optional[UUID]
    status_code: int
    ip: Optional[str]
    created_at: datetime
    details: Optional[dict]


# ==================== MANAGEMENT DASHBOARD ====================

class ManagerDashboard(BaseModel):
    department: Optional[str]
    users_total: int
    active_users: int
    completed_attempts: int
    passed_attempts: int
    pass_rate: Optional[float]
    overdue_assignments: int
    overdue_course_enrollments: int
    mandatory_tests_total: int
    mandatory_not_passed_pairs: int
    certificates_total: int
    avg_course_progress: Optional[float]


class MandatoryRiskItem(BaseModel):
    user_id: UUID
    full_name: str
    department: Optional[str]
    test_id: UUID
    test_title: str


class OverdueItem(BaseModel):
    id: UUID
    kind: str
    user_id: UUID
    full_name: str
    department: Optional[str]
    object_type: str
    object_id: Optional[UUID]
    title: Optional[str]
    due_date: datetime


class UserProgressItem(BaseModel):
    user_id: UUID
    full_name: str
    department: Optional[str]
    completed_attempts: int
    passed_attempts: int
    views: int
    assignments_total: int
    assignments_completed: int
    course_enrollments_total: int
    course_enrollments_completed: int
    avg_course_progress: Optional[float]