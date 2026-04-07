from providers.replicate_provider import run_idm_vton


async def run_tryon(person_image_url: str, garment_image_url: str) -> str:
    """
    Business-level try-on operation.
    Returns the composite image URL.
    """
    composite_url = await run_idm_vton(
        person_image_url=person_image_url,
        garment_image_url=garment_image_url,
    )
    if not composite_url:
        raise RuntimeError("Try-on produced no output")
    return composite_url

