import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from models.schemas import RecommendRequest, RecommendResponse
from services.recommend_service import generate_recommendations

router = APIRouter(prefix="/api/v1/recommend", tags=["recommend"])
logger = logging.getLogger(__name__)


@router.post("", response_model=RecommendResponse)
async def get_recommendations(
    request: RecommendRequest,
    db: Session = Depends(get_db),
):
    try:
        logger.info("recommendation requested")
        return await generate_recommendations(
            db,
            request.user_id,
            request.weather_condition,
            request.mood,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recommendation failed: {e}",
        ) from e
