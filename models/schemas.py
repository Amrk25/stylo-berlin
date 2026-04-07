from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from typing import List


class WardrobeItemCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=128)
    color: str = Field(..., min_length=1, max_length=128)
    image_url: str = Field(..., min_length=1, max_length=2048)


class WardrobeItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    name: str
    category: str
    color: str
    image_url: str
    created_at: datetime


class WardrobeItemListResponse(BaseModel):
    items: List[WardrobeItemRead]

class RecommendItem(BaseModel):
    item_id: str
    description: str

class OutfitRecommendation(BaseModel):
    outfits: List[RecommendItem]
    rationale: str

class RecommendRequest(BaseModel):
    user_id: str
    weather_condition: str
    mood: str

class RecommendResponse(BaseModel):
    recommendations: List[OutfitRecommendation]

class TryOnRequest(BaseModel):
    person_image_url: str
    garment_image_url: str

class TryOnResponse(BaseModel):
    composite_image_url: str
