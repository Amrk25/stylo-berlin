import logging

from fastapi import APIRouter, HTTPException, status
from models.schemas import TryOnRequest, TryOnResponse
from services.tryon_service import run_tryon

router = APIRouter(prefix="/api/v1/try-on", tags=["try-on"])
logger = logging.getLogger(__name__)

@router.post("", response_model=TryOnResponse)
async def try_on_garment(request: TryOnRequest):
    try:
        logger.info("try-on requested")
        composite_image_url = await run_tryon(
            request.person_image_url, request.garment_image_url
        )
        return TryOnResponse(composite_image_url=composite_image_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Try-on generation failed: {e}",
        )
