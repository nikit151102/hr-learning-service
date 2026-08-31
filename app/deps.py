from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User, UserRole


def get_by_id_max_or_create(db: Session, id_max: str) -> Optional[User]:
    user = db.query(User).filter(User.id_max == id_max).first()
    if user:
        return user

    if settings.auto_create_user_by_id_max:
        user = User(
            id_max=id_max,
            full_name="Unknown",
            role=UserRole.employee,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return None


def get_current_user(
    x_id_max: Optional[str] = Header(default=None, alias="X-Id-Max"),
    db: Session = Depends(get_db),
) -> User:
    if not x_id_max:
        raise HTTPException(status_code=401, detail="X-Id-Max header is required")

    user = get_by_id_max_or_create(db, x_id_max)

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


def require_roles(*allowed_roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role == UserRole.admin:
            return current_user

        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient role")

        return current_user

    return checker


HRRequired = require_roles(UserRole.hr)
AdminRequired = require_roles(UserRole.admin)


def get_or_404(db: Session, model, object_id):
    obj = db.get(model, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return obj


def paginate(query, page: int = 1, size: int = 20):
    page = max(page, 1)
    size = max(min(size, 100), 1)

    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    }