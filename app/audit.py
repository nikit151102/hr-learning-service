from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import AdminRequired, paginate
from app.enterprise_models import AuditLog
from app.enterprise_schemas import AuditLogRead
from app.schemas import Page


router = APIRouter(prefix="/audit", tags=["Аудит"])


@router.get(
    "",
    response_model=Page[AuditLogRead],
    summary="Журнал аудита",
    description="Список действий пользователей и администраторов.",
)
def list_audit_logs(
    user_id: UUID | None = Query(default=None, description="Фильтр по пользователю"),
    method: str | None = Query(default=None, description="HTTP-метод"),
    path: str | None = Query(default=None, description="Часть пути"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(AdminRequired),
):
    query = db.query(AuditLog)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    if method:
        query = query.filter(AuditLog.method == method.upper())

    if path:
        query = query.filter(AuditLog.path.ilike(f"%{path}%"))

    query = query.order_by(AuditLog.created_at.desc())

    return paginate(query, page, size)