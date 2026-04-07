from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from db.session import get_db
from models.schemas import (
    WardrobeItemCreate,
    WardrobeItemListResponse,
    WardrobeItemRead,
)
from services import wardrobe_service

router = APIRouter(prefix="/api/v1/wardrobe", tags=["wardrobe"])


@router.post("", response_model=WardrobeItemRead, status_code=status.HTTP_201_CREATED)
def create_wardrobe_item(
    payload: WardrobeItemCreate,
    db: Session = Depends(get_db),
):
    row = wardrobe_service.create_item(db, payload)
    return WardrobeItemRead.model_validate(row)


@router.get("", response_model=WardrobeItemListResponse)
def list_wardrobe_items(
    user_id: str = Query(..., min_length=1, description="Owner of the wardrobe"),
    db: Session = Depends(get_db),
):
    rows = wardrobe_service.list_items_for_user(db, user_id)
    return WardrobeItemListResponse(
        items=[WardrobeItemRead.model_validate(r) for r in rows]
    )


@router.get("/{item_id}", response_model=WardrobeItemRead)
def get_wardrobe_item(
    item_id: int,
    user_id: str | None = Query(
        default=None,
        min_length=1,
        description="If set, the item must belong to this user",
    ),
    db: Session = Depends(get_db),
):
    row = wardrobe_service.get_item_by_id(db, item_id, user_id=user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return WardrobeItemRead.model_validate(row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wardrobe_item(
    item_id: int,
    user_id: str | None = Query(
        default=None,
        min_length=1,
        description="If set, only delete when the item belongs to this user",
    ),
    db: Session = Depends(get_db),
):
    deleted = wardrobe_service.delete_item(db, item_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
