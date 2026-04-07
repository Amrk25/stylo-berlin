from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db_models import WardrobeItem
from models.schemas import WardrobeItemCreate


def create_item(db: Session, payload: WardrobeItemCreate) -> WardrobeItem:
    row = WardrobeItem(
        user_id=payload.user_id,
        name=payload.name,
        category=payload.category,
        color=payload.color,
        image_url=payload.image_url,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_items_for_user(db: Session, user_id: str) -> list[WardrobeItem]:
    stmt = (
        select(WardrobeItem)
        .where(WardrobeItem.user_id == user_id)
        .order_by(WardrobeItem.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def get_item_by_id(
    db: Session, item_id: int, user_id: str | None = None
) -> WardrobeItem | None:
    stmt = select(WardrobeItem).where(WardrobeItem.id == item_id)
    if user_id is not None:
        stmt = stmt.where(WardrobeItem.user_id == user_id)
    return db.scalars(stmt).first()


def delete_item(
    db: Session, item_id: int, user_id: str | None = None
) -> bool:
    item = get_item_by_id(db, item_id, user_id=user_id)
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True
