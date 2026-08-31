from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Category
from app.schemas import CategoryRead, CategoryTree


def assert_parent_exists(db: Session, parent_id: UUID | None) -> None:
    if parent_id is None:
        return

    if not db.get(Category, parent_id):
        raise HTTPException(status_code=404, detail="Parent category not found")


def assert_name_unique(
    db: Session,
    parent_id: UUID | None,
    name: str,
    exclude_id: UUID | None = None,
) -> None:
    query = db.query(Category).filter(Category.name == name)

    if parent_id is None:
        query = query.filter(Category.parent_id.is_(None))
    else:
        query = query.filter(Category.parent_id == parent_id)

    if exclude_id:
        query = query.filter(Category.id != exclude_id)

    if query.first():
        raise HTTPException(
            status_code=409,
            detail="Category with this name already exists in this parent",
        )


def ensure_no_cycle(
    db: Session,
    category_id: UUID,
    new_parent_id: UUID | None,
) -> None:
    if new_parent_id is None:
        return

    if new_parent_id == category_id:
        raise HTTPException(status_code=422, detail="Cannot set parent to itself")

    current = db.get(Category, new_parent_id)

    while current:
        if current.id == category_id:
            raise HTTPException(status_code=422, detail="Category cycle detected")

        if current.parent_id is None:
            break

        current = db.get(Category, current.parent_id)


def build_tree(db: Session, parent_id: UUID | None = None) -> list[CategoryTree]:
    categories = (
        db.query(Category)
        .order_by(Category.sort_order, Category.name)
        .all()
    )

    children_map = defaultdict(list)
    for category in categories:
        children_map[category.parent_id].append(category)

    def build(pid: UUID | None) -> list[CategoryTree]:
        nodes = []

        for category in children_map.get(pid, []):
            read = CategoryRead.model_validate(category)
            node = CategoryTree(**read.model_dump(), children=[])
            node.children = build(category.id)
            nodes.append(node)

        return nodes

    return build(parent_id)