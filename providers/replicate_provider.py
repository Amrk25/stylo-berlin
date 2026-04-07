import asyncio
import os
from typing import Any

import httpx


REPLICATE_API_BASE = "https://api.replicate.com/v1"
REPLICATE_PREDICTIONS_URL = f"{REPLICATE_API_BASE}/predictions"

# Official model prediction endpoint (supports POST /v1/models/.../predictions)
REPLICATE_LLAMA_PREDICTIONS_URL = (
    f"{REPLICATE_API_BASE}/models/meta/meta-llama-3-8b-instruct/predictions"
)

# Community model (needs /v1/predictions + version id)
REPLICATE_IDM_VTON_MODEL_PATH = "/models/cuuupid/idm-vton"


class ReplicateError(RuntimeError):
    pass


def _auth_headers() -> dict[str, str]:
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token:
        raise ReplicateError("Missing REPLICATE_API_TOKEN environment variable")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _poll_prediction(
    client: httpx.AsyncClient,
    get_url: str,
    headers: dict[str, str],
    *,
    max_wait_seconds: float,
) -> dict[str, Any]:
    start = asyncio.get_running_loop().time()
    delay = 0.5
    last_status: str | None = None

    while True:
        poll_resp = await client.get(get_url, headers=headers)
        if poll_resp.status_code not in (200, 201):
            raise ReplicateError(
                f"Replicate poll prediction error HTTP {poll_resp.status_code}: {poll_resp.text}"
            )

        data = poll_resp.json()
        if not isinstance(data, dict):
            raise ReplicateError("Unexpected Replicate polling response shape")

        prediction_status = data.get("status")
        if isinstance(prediction_status, str):
            last_status = prediction_status

        if prediction_status == "succeeded":
            return data
        if prediction_status == "failed":
            raise ReplicateError(f"Replicate prediction failed: {data.get('error')}")
        if prediction_status in {"canceled", "cancelled"}:
            raise ReplicateError("Replicate prediction was canceled")

        now = asyncio.get_running_loop().time()
        if (now - start) > max_wait_seconds:
            raise ReplicateError(f"Replicate prediction timed out (last_status={last_status})")

        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 3.0)


async def run_idm_vton(
    *,
    person_image_url: str,
    garment_image_url: str,
    garment_des: str = "a piece of clothing",
    max_wait_seconds: float = 180.0,
) -> str:
    """
    Runs IDM-VTON on Replicate and returns the final output image URL.
    """
    headers = _auth_headers()
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        model_resp = await client.get(f"{REPLICATE_API_BASE}{REPLICATE_IDM_VTON_MODEL_PATH}", headers=headers)
        if model_resp.status_code != 200:
            raise ReplicateError(
                f"Replicate model lookup error HTTP {model_resp.status_code}: {model_resp.text}"
            )

        model_data = model_resp.json()
        if not isinstance(model_data, dict):
            raise ReplicateError("Unexpected Replicate model response shape")
        latest = model_data.get("latest_version")
        if not isinstance(latest, dict):
            raise ReplicateError("Replicate model has no latest_version")
        version_id = latest.get("id")
        if not isinstance(version_id, str) or not version_id.strip():
            raise ReplicateError("Replicate latest_version missing id")

        create_payload = {
            "version": version_id,
            "input": {
                "human_img": person_image_url,
                "garm_img": garment_image_url,
                "garment_des": garment_des,
            },
        }

        create_resp = await client.post(REPLICATE_PREDICTIONS_URL, headers=headers, json=create_payload)
        if create_resp.status_code not in (200, 201):
            raise ReplicateError(
                f"Replicate create prediction error HTTP {create_resp.status_code}: {create_resp.text}"
            )

        create_data = create_resp.json()
        get_url = (create_data.get("urls") or {}).get("get") if isinstance(create_data, dict) else None
        if not get_url or not isinstance(get_url, str):
            raise ReplicateError("Replicate response missing prediction get URL")

        prediction = await _poll_prediction(
            client, get_url, headers, max_wait_seconds=max_wait_seconds
        )

        output = prediction.get("output")
        if isinstance(output, list) and output:
            return str(output[-1])
        if isinstance(output, str) and output:
            return output

        raise ReplicateError("Replicate returned empty output")


async def run_llama_recommendation(
    *,
    prompt: str,
    system_prompt: str,
    max_tokens: int = 512,
    max_wait_seconds: float = 120.0,
) -> str:
    """
    Runs Llama 3 8B Instruct on Replicate and returns the raw text output.
    Replicate may return an array of chunks; we join them into a single string.
    """
    headers = _auth_headers()
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        create_payload = {
            "input": {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
            }
        }
        create_resp = await client.post(
            REPLICATE_LLAMA_PREDICTIONS_URL, headers=headers, json=create_payload
        )
        if create_resp.status_code not in (200, 201):
            raise ReplicateError(
                f"Replicate create prediction error HTTP {create_resp.status_code}: {create_resp.text}"
            )

        create_data = create_resp.json()
        get_url = (create_data.get("urls") or {}).get("get") if isinstance(create_data, dict) else None
        if not get_url or not isinstance(get_url, str):
            raise ReplicateError("Replicate response missing prediction get URL")

        prediction = await _poll_prediction(
            client, get_url, headers, max_wait_seconds=max_wait_seconds
        )

        output = prediction.get("output")
        if isinstance(output, str):
            return output
        if isinstance(output, list):
            return "".join(str(part) for part in output)
        if output is None:
            return ""
        return str(output)

