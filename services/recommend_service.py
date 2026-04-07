import json
import logging
from collections import defaultdict
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from models.db_models import WardrobeItem
from models.schemas import OutfitRecommendation, RecommendItem, RecommendResponse
from providers.replicate_provider import ReplicateError, run_llama_recommendation
from services import wardrobe_service

logger = logging.getLogger(__name__)

LLM_SHORTLIST_MAX = 12


def _extract_json_object(text: str) -> dict[str, Any]:
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()

    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(s[start : end + 1])


def _category_bucket(item: WardrobeItem) -> str:
    c = (item.category or "").lower()
    n = (item.name or "").lower()
    text = f"{c} {n}"

    if any(k in text for k in ("outerwear", "coat", "jacket", "parka", "anorak", "shell")):
        return "outerwear"
    if any(k in text for k in ("top", "shirt", "tee", "t-shirt", "blouse", "sweater", "knit", "hoodie")):
        return "tops"
    if any(k in text for k in ("bottom", "jean", "trouser", "pant", "skirt", "short")):
        return "bottoms"
    if any(k in text for k in ("shoe", "boot", "sneaker", "footwear", "loafer")):
        return "footwear"
    if any(k in text for k in ("accessory", "belt", "bag", "hat", "scarf", "harness", "jewelry")):
        return "accessories"
    return "other"


def _score_item(item: WardrobeItem, weather_condition: str, mood: str) -> float:
    w = (weather_condition or "").lower()
    m = (mood or "").lower()
    name = (item.name or "").lower()
    cat = (item.category or "").lower()
    blob = f"{name} {cat}"
    bucket = _category_bucket(item)
    score = 0.0

    if any(k in w for k in ("rain", "raining", "drizzle", "storm", "wet", "downpour")):
        if any(k in blob for k in ("rain", "waterproof", "shell", "gore", "parka", "anorak")):
            score += 4.0
        if bucket == "outerwear":
            score += 1.5

    if any(k in w for k in ("cold", "freez", "snow", "winter", "chilly", "ice", "°c", "degrees")):
        if any(k in blob for k in ("wool", "coat", "puffer", "down", "fleece", "warm")):
            score += 3.0
        if bucket == "outerwear":
            score += 2.0

    if any(k in w for k in ("hot", "heat", "humid", "summer", "sun", "warm day")):
        if bucket == "tops":
            score += 1.5
        if bucket == "outerwear" and any(k in blob for k in ("heavy", "wool", "down", "puffer")):
            score -= 2.0

    if any(k in m for k in ("relax", "chill", "calm", "cozy", "lazy", "easy")):
        if any(k in blob for k in ("tee", "t-shirt", "jean", "knit", "hoodie", "sweat")):
            score += 2.0
        if bucket in ("tops", "bottoms"):
            score += 0.5

    if any(k in m for k in ("bold", "party", "club", "techno", "night", "edgy", "statement")):
        if bucket == "accessories":
            score += 3.0
        if any(k in blob for k in ("harness", "leather", "metallic", "sequin")):
            score += 2.0

    if bucket == "other":
        score -= 0.25

    return score


def _shortlist_for_llm(items: list[WardrobeItem], weather: str, mood: str) -> list[WardrobeItem]:
    ranked = sorted(items, key=lambda i: _score_item(i, weather, mood), reverse=True)
    seen: set[int] = set()
    out: list[WardrobeItem] = []
    for it in ranked:
        if it.id in seen:
            continue
        seen.add(it.id)
        out.append(it)
        if len(out) >= LLM_SHORTLIST_MAX:
            break
    return out


def _item_to_recommend_item(item: WardrobeItem) -> RecommendItem:
    desc = f"{item.name} — {item.category}, {item.color}"
    return RecommendItem(item_id=str(item.id), description=desc)


def _rationale_stub(weather_condition: str, mood: str, picked: list[WardrobeItem]) -> str:
    names = ", ".join(i.name for i in picked[:4])
    if len(picked) > 4:
        names += ", …"
    return (
        f"Berlin-ready mix for “{mood}” in “{weather_condition}”. "
        f"Built from your saved wardrobe: {names}."
    )


def _build_deterministic_recommendations(
    items: list[WardrobeItem], weather_condition: str, mood: str
) -> RecommendResponse:
    if not items:
        return RecommendResponse(recommendations=[])

    by_bucket: dict[str, list[WardrobeItem]] = defaultdict(list)
    for it in items:
        by_bucket[_category_bucket(it)].append(it)

    for b in by_bucket:
        by_bucket[b].sort(
            key=lambda i: _score_item(i, weather_condition, mood), reverse=True
        )

    def pick(bucket: str, skip_ids: set[int]) -> WardrobeItem | None:
        for cand in by_bucket.get(bucket, []):
            if cand.id not in skip_ids:
                return cand
        return None

    def assemble_outfit(skip_ids: set[int]) -> list[WardrobeItem] | None:
        used: set[int] = set(skip_ids)
        outfit: list[WardrobeItem] = []

        o = pick("outerwear", used)
        if o:
            outfit.append(o)
            used.add(o.id)

        for bucket in ("tops", "bottoms", "footwear", "accessories"):
            p = pick(bucket, used)
            if p:
                outfit.append(p)
                used.add(p.id)

        if not outfit:
            best = max(items, key=lambda i: _score_item(i, weather_condition, mood))
            return [best]

        return outfit

    outfits_a = assemble_outfit(set())
    if not outfits_a:
        return RecommendResponse(recommendations=[])

    used_ids = {i.id for i in outfits_a}
    outfits_b = assemble_outfit(used_ids)

    recs: list[OutfitRecommendation] = [
        OutfitRecommendation(
            outfits=[_item_to_recommend_item(i) for i in outfits_a],
            rationale=_rationale_stub(weather_condition, mood, outfits_a),
        )
    ]

    if outfits_b and {i.id for i in outfits_b} != {i.id for i in outfits_a}:
        recs.append(
            OutfitRecommendation(
                outfits=[_item_to_recommend_item(i) for i in outfits_b],
                rationale=_rationale_stub(weather_condition, mood, outfits_b)
                + " Alternate pairing from the same closet.",
            )
        )

    return RecommendResponse(recommendations=recs)


def _empty_wardrobe_response() -> RecommendResponse:
    return RecommendResponse(
        recommendations=[
            OutfitRecommendation(
                outfits=[],
                rationale=(
                    "No saved wardrobe items yet for this user. "
                    "Add pieces with POST /api/v1/wardrobe, then try again."
                ),
            )
        ]
    )


def _sanitize_llm_response(
    data: dict[str, Any],
    allowed_by_id: dict[str, WardrobeItem],
    weather_condition: str,
    mood: str,
) -> RecommendResponse | None:
    try:
        parsed = RecommendResponse.model_validate(data)
    except ValidationError:
        return None

    cleaned: list[OutfitRecommendation] = []
    for block in parsed.recommendations:
        kept: list[RecommendItem] = []
        for o in block.outfits:
            sid = str(o.item_id).strip()
            src = allowed_by_id.get(sid)
            if src is None:
                continue
            desc = (o.description or "").strip() or _item_to_recommend_item(src).description
            kept.append(RecommendItem(item_id=sid, description=desc))
        if kept:
            picked_rows = [
                allowed_by_id[o.item_id] for o in kept if o.item_id in allowed_by_id
            ]
            rationale_text = (block.rationale or "").strip()
            if not rationale_text:
                rationale_text = _rationale_stub(weather_condition, mood, picked_rows)
            cleaned.append(
                OutfitRecommendation(
                    outfits=kept,
                    rationale=rationale_text,
                )
            )

    if not cleaned:
        return None
    return RecommendResponse(recommendations=cleaned)


async def _try_llm_recommendations(
    *,
    user_id: str,
    weather_condition: str,
    mood: str,
    shortlist: list[WardrobeItem],
) -> RecommendResponse | None:
    if not shortlist:
        return None

    payload = [
        {
            "id": str(i.id),
            "name": i.name,
            "category": i.category,
            "color": i.color,
        }
        for i in shortlist
    ]
    allowed = {str(i.id): i for i in shortlist}
    wardrobe_json = json.dumps(payload, ensure_ascii=False)

    prompt = f"""User:
- user_id: {user_id!r}
- weather_condition: {weather_condition!r}
- mood: {mood!r}

Shortlisted wardrobe (JSON). You MUST NOT invent items. Every item_id in your answer MUST be one of the "id" values below.
{wardrobe_json}

Return ONLY valid JSON (no markdown) with this exact shape:
{{
  "recommendations": [
    {{
      "outfits": [
        {{ "item_id": "<one of the ids above>", "description": "<short stylist line>" }}
      ],
      "rationale": "<Berlin-specific, ties weather + mood together>"
    }}
  ]
}}

Use 1–2 recommendation blocks. Prefer coherent outfits (outer layer / top / bottom / shoes when available)."""

    raw_text = await run_llama_recommendation(
        prompt=prompt,
        system_prompt=(
            "You are a Berlin fashion stylist. Output ONLY raw valid JSON. "
            "Never invent item ids. No markdown."
        ),
        max_tokens=512,
    )
    if not raw_text.strip():
        return None

    parsed = _extract_json_object(raw_text)
    return _sanitize_llm_response(
        parsed, allowed, weather_condition, mood
    )


async def generate_recommendations(
    db: Session,
    user_id: str,
    weather_condition: str,
    mood: str,
) -> RecommendResponse:
    items = wardrobe_service.list_items_for_user(db, user_id)

    if not items:
        return _empty_wardrobe_response()

    deterministic = _build_deterministic_recommendations(items, weather_condition, mood)
    shortlist = _shortlist_for_llm(items, weather_condition, mood)

    try:
        llm_result = await _try_llm_recommendations(
            user_id=user_id,
            weather_condition=weather_condition,
            mood=mood,
            shortlist=shortlist,
        )
        if llm_result is not None:
            return llm_result
    except (ReplicateError, ValueError, json.JSONDecodeError, KeyError, TypeError) as e:
        logger.info("LLM recommendation skipped, using deterministic fallback: %s", e)
    except Exception as e:
        logger.warning("Unexpected error during LLM recommendation: %s", e)

    return deterministic
