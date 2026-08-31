import asyncio
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.analytics import router as analytics_router
from app.api import router as api_router
from app.assignments import router as assignments_router
from app.audit import router as audit_router
from app.certificates import router as certificates_router
from app.core.config import settings
from app.courses import router as courses_router
from app.dashboard import router as dashboard_router
from app.db.session import Base, SessionLocal, engine
from app.enterprise_models import AuditLog
from app.feedback import router as feedback_router
from app.jobs import setup_scheduler, shutdown_scheduler
from app.management import router as management_router
from app.models import User, UserRole
from app.notifications import router as notifications_router
from app.services import minio_service
from app.swagger_ru import apply_russian_docs


UUID_REGEX = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


tags_metadata = [
    {
        "name": "Служебные",
        "description": "Проверка доступности сервиса и зависимостей.",
    },
    {
        "name": "Авторизация",
        "description": "Вход без пароля по idMax и данные текущего пользователя.",
    },
    {
        "name": "Текущий пользователь",
        "description": "Личные данные, назначения, попытки, уведомления и сводка пользователя.",
    },
    {
        "name": "Пользователи",
        "description": "Управление пользователями, поиск, роли и профили.",
    },
    {
        "name": "Категории",
        "description": "Категории и подкатегории учебных материалов.",
    },
    {
        "name": "Материалы",
        "description": "Учебные материалы, файлы, ссылки и просмотры.",
    },
    {
        "name": "Файлы",
        "description": "Загрузка файлов в MinIO.",
    },
    {
        "name": "Тесты",
        "description": "Тесты, вопросы, ответы и градации результатов.",
    },
    {
        "name": "Попытки",
        "description": "Прохождение тестов и результаты пользователей.",
    },
    {
        "name": "Назначения",
        "description": "Назначение материалов и тестов пользователям.",
    },
    {
        "name": "Отзывы",
        "description": "Оценки и комментарии к материалам.",
    },
    {
        "name": "Аналитика",
        "description": "Статистика, дашборды, топы и экспорт данных.",
    },
    {
        "name": "Курсы",
        "description": "Планы обучения, состав курсов и прогресс прохождения.",
    },
    {
        "name": "Сертификаты",
        "description": "Выдача, скачивание и проверка сертификатов.",
    },
    {
        "name": "Уведомления",
        "description": "Уведомления пользователя о назначениях, дедлайнах и результатах.",
    },
    {
        "name": "Управление",
        "description": "Дашборд руководителя, отделы, обязательные тесты и риски.",
    },
    {
        "name": "Аудит",
        "description": "Журнал действий пользователей и администраторов.",
    },
]


def init_db() -> None:
    from app import enterprise_models, ext_models, models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def bootstrap_admin() -> None:
    if not settings.bootstrap_admin_id_max:
        return

    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .filter(User.id_max == settings.bootstrap_admin_id_max)
            .first()
        )

        if not user:
            user = User(
                id_max=settings.bootstrap_admin_id_max,
                full_name=settings.bootstrap_admin_full_name,
                role=UserRole.admin,
                is_active=True,
            )
            db.add(user)
            db.commit()
        elif user.role != UserRole.admin:
            user.role = UserRole.admin
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    for _ in range(30):
        try:
            minio_service.ensure_bucket()
            break
        except Exception:
            await asyncio.sleep(1)
    else:
        raise RuntimeError("MinIO is not available")

    init_db()
    bootstrap_admin()

    try:
        setup_scheduler()
    except Exception:
        pass

    yield

    try:
        shutdown_scheduler()
    except Exception:
        pass


app = FastAPI(
    title="HR Learning Service",
    description="""
    Корпоративная платформа обучения и тестирования.

    Возможности:
    - учебные материалы и категории;
    - файлы в MinIO;
    - тесты с вопросами, ответами и градациями;
    - попытки и лимиты прохождений;
    - назначения пользователям;
    - курсы и планы обучения;
    - сертификаты с PDF и проверкой подлинности;
    - уведомления;
    - обязательные тесты;
    - дашборд руководителя;
    - аналитика и экспорт;
    - аудит действий.
    """,
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    response = await call_next(request)

    try:
        if request.method in {"POST", "PATCH", "DELETE"} and request.url.path.startswith(
            "/api/v1"
        ):
            db: Session = SessionLocal()

            try:
                id_max = request.headers.get("X-Id-Max")
                user = None

                if id_max:
                    user = db.query(User).filter(User.id_max == id_max).first()

                parts = request.url.path.split("/")
                entity_type = parts[3] if len(parts) > 3 else None

                ids = UUID_REGEX.findall(request.url.path)
                entity_id = uuid.UUID(ids[-1]) if ids else None

                details = None
                if request.url.query:
                    details = {"query": str(request.url.query)}

                db.add(
                    AuditLog(
                        user_id=user.id if user else None,
                        method=request.method,
                        path=request.url.path,
                        action=request.method,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        status_code=response.status_code,
                        ip=request.client.host if request.client else None,
                        details=details,
                    )
                )

                db.commit()
            finally:
                db.close()
    except Exception:
        pass

    return response


app.include_router(api_router)
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(assignments_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(courses_router, prefix="/api/v1")
app.include_router(certificates_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(management_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")

apply_russian_docs(app)


@app.get("/", include_in_schema=False)
def root():
    return {
        "docs": "/docs",
        "health": "/api/v1/health",
    }