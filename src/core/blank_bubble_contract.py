"""Small wire contract for detecting speech-bubble slots without OCR."""

from __future__ import annotations

import math
from typing import Any, Mapping

from PIL import Image

from src.core.mtu_worker_contract import (
    MtuWorkerContractError,
    encode_worker_png,
)
from src.core.native_mtu_page_contract import PINNED_MTU_REVISION


BLANK_BUBBLE_CONTRACT_VERSION = "saber-blank-bubbles/v1"
DEFAULT_BUBBLE_CONFIDENCE = 0.25
DEFAULT_BUBBLE_IMAGE_SIZE = 1600


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise MtuWorkerContractError(f"{name} 必须是有限数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise MtuWorkerContractError(f"{name} 必须是有限数字") from error
    if not math.isfinite(number):
        raise MtuWorkerContractError(f"{name} 必须是有限数字")
    return number


def validate_bubble_options(value: Any) -> dict[str, float | int]:
    if not isinstance(value, Mapping) or set(value) - {"confidence", "image_size"}:
        raise MtuWorkerContractError("气泡检测选项无效")
    confidence = _number(
        value.get("confidence", DEFAULT_BUBBLE_CONFIDENCE), "confidence"
    )
    image_size = value.get("image_size", DEFAULT_BUBBLE_IMAGE_SIZE)
    if not 0 < confidence <= 1:
        raise MtuWorkerContractError("confidence 必须在 0 到 1 之间")
    if isinstance(image_size, bool) or not isinstance(image_size, int) or not 640 <= image_size <= 2560:
        raise MtuWorkerContractError("image_size 必须是 640 到 2560 的整数")
    return {"confidence": confidence, "image_size": image_size}


def build_bubble_detect_request(
    image: Image.Image, options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "contract_version": BLANK_BUBBLE_CONTRACT_VERSION,
        "operation": "detect_bubbles",
        "image": encode_worker_png(image.convert("RGB")),
        "options": validate_bubble_options(options or {}),
    }


def normalize_bubble_detect_response(
    payload: Any, *, image_size: tuple[int, int]
) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        raise MtuWorkerContractError("气泡检测响应必须是对象")
    if (
        payload.get("contract_version") != BLANK_BUBBLE_CONTRACT_VERSION
        or payload.get("operation") != "detect_bubbles"
        or payload.get("mtu_revision") != PINNED_MTU_REVISION
    ):
        raise MtuWorkerContractError("气泡检测响应版本或 MTU revision 不匹配")
    if (payload.get("image_width"), payload.get("image_height")) != image_size:
        raise MtuWorkerContractError("气泡检测响应图片尺寸不匹配")
    raw_slots = payload.get("slots")
    if not isinstance(raw_slots, list) or len(raw_slots) > 128:
        raise MtuWorkerContractError("气泡检测响应 slots 无效")
    width, height = image_size
    slots = []
    for index, raw in enumerate(raw_slots):
        if not isinstance(raw, Mapping) or set(raw) != {"coords", "confidence"}:
            raise MtuWorkerContractError(f"slots[{index}] 字段无效")
        coords = raw["coords"]
        if not isinstance(coords, list) or len(coords) != 4:
            raise MtuWorkerContractError(f"slots[{index}] 坐标无效")
        values = [_number(item, f"slots[{index}].coords") for item in coords]
        x1, y1, x2, y2 = values
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise MtuWorkerContractError(f"slots[{index}] 越过图片边界")
        confidence = _number(raw["confidence"], f"slots[{index}].confidence")
        if not 0 <= confidence <= 1:
            raise MtuWorkerContractError(f"slots[{index}] 置信度无效")
        rounded = [int(round(value)) for value in values]
        if not (0 <= rounded[0] < rounded[2] <= width and 0 <= rounded[1] < rounded[3] <= height):
            raise MtuWorkerContractError(f"slots[{index}] 四舍五入后坐标无效")
        slots.append({
            "coords": rounded,
            "confidence": confidence,
        })
    return slots
