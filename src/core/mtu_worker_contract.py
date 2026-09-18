"""Versioned, vendor-free payload contract for a pinned MTU worker.

The worker may run in Modal or another isolated environment, but neither a
Modal object nor an MTU ``TextBlock`` crosses this boundary.  The payloads are
plain JSON-compatible dictionaries so a fake client can exercise the complete
adapter contract without a GPU or an external request.
"""

import base64
import io
import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import numpy as np
from PIL import Image

from src.core.ocr_types import OcrResult


MTU_WORKER_CONTRACT_VERSION = "saber-mtu-worker/v1"


class MtuWorkerContractError(ValueError):
    """Raised for an invalid request or incompatible MTU worker response."""


_DETECT_OPTION_KEYS = {
    "detector_type",
    "expand_ratio",
    "expand_top",
    "expand_bottom",
    "expand_left",
    "expand_right",
    "enable_aux_yolo_detection",
    "aux_yolo_conf_threshold",
    "aux_yolo_overlap_threshold",
    "enable_saber_yolo_refine",
    "saber_yolo_refine_overlap_threshold",
    "min_text_block_area_percent",
}
_OCR_OPTION_KEYS = {
    "source_language",
    "ocr_engine",
    "textlines_per_bubble",
    "enable_hybrid_ocr",
    "secondary_ocr_engine",
    "hybrid_ocr_threshold",
}
_SENSITIVE_OPTION_KEYS = {
    "baidu_api_key",
    "baidu_secret_key",
    "ai_vision_api_key",
    "custom_ai_vision_base_url",
    "ai_vision_openai_options",
}


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MtuWorkerContractError(f"MTU Worker {name} 必须是对象")
    return value


def _require_stage_response(payload: Mapping[str, Any], stage: str) -> None:
    version = payload.get("contract_version")
    if version != MTU_WORKER_CONTRACT_VERSION:
        raise MtuWorkerContractError(
            f"MTU Worker 契约版本不兼容: {version or '<empty>'}"
        )
    if payload.get("stage") != stage:
        raise MtuWorkerContractError(
            f"MTU Worker 返回了错误阶段: {payload.get('stage') or '<empty>'}"
        )


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise MtuWorkerContractError(f"{field} 必须是数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise MtuWorkerContractError(f"{field} 必须是数字") from error
    if not math.isfinite(number):
        raise MtuWorkerContractError(f"{field} 必须是有限数字")
    return number


def _coords(value: Any, field: str) -> List[int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        raise MtuWorkerContractError(f"{field} 必须是四个坐标")
    coords = [int(round(_number(item, f"{field}[{index}]"))) for index, item in enumerate(value)]
    if coords[0] >= coords[2] or coords[1] >= coords[3]:
        raise MtuWorkerContractError(f"{field} 必须满足 x1 < x2 且 y1 < y2")
    return coords


def _image_payload(image: Image.Image) -> Dict[str, Any]:
    if not isinstance(image, Image.Image):
        raise MtuWorkerContractError("MTU Worker 只接受 PIL 图片对象")
    normalized = image.convert("RGB")
    buffer = io.BytesIO()
    normalized.save(buffer, format="PNG")
    return {
        "media_type": "image/png",
        "encoding": "base64",
        "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "width": normalized.width,
        "height": normalized.height,
    }


def _safe_options(options: Mapping[str, Any], allowed_keys: Iterable[str]) -> Dict[str, Any]:
    sensitive = sorted(key for key in _SENSITIVE_OPTION_KEYS if options.get(key))
    if sensitive:
        raise MtuWorkerContractError(
            "modal_mtu 不接受调用方 API 凭据或远程地址: " + ", ".join(sensitive)
        )
    return {
        key: options[key]
        for key in allowed_keys
        if key in options and options[key] is not None
    }


def build_mtu_detect_request(image: Image.Image, options: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the complete JSON payload for one MTU detection request."""

    return {
        "contract_version": MTU_WORKER_CONTRACT_VERSION,
        "stage": "detect",
        "image": _image_payload(image),
        "options": _safe_options(options, _DETECT_OPTION_KEYS),
    }


def build_mtu_ocr_request(
    image: Image.Image,
    bubble_coords: Sequence[Any],
    options: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build a stable-ID OCR request without passing MTU text objects upstream."""

    textlines = options.get("textlines_per_bubble") or []
    if not isinstance(textlines, Sequence) or isinstance(textlines, (str, bytes)):
        raise MtuWorkerContractError("textlines_per_bubble 必须是区域数组")
    regions = []
    for index, coord in enumerate(bubble_coords):
        region_textlines = textlines[index] if index < len(textlines) else []
        if not isinstance(region_textlines, list):
            raise MtuWorkerContractError(f"textlines_per_bubble[{index}] 必须是数组")
        regions.append({
            "id": f"region-{index}",
            "coords": _coords(coord, f"regions[{index}].coords"),
            "textlines": region_textlines,
        })
    return {
        "contract_version": MTU_WORKER_CONTRACT_VERSION,
        "stage": "ocr",
        "image": _image_payload(image),
        "regions": regions,
        "options": _safe_options(options, _OCR_OPTION_KEYS),
    }


def _decode_mask(payload: Any, expected_width: int, expected_height: int) -> np.ndarray:
    mask = _require_mapping(payload, "text_mask")
    if mask.get("media_type") != "image/png" or mask.get("encoding") != "base64":
        raise MtuWorkerContractError("MTU Worker text_mask 必须是 base64 PNG")
    data = mask.get("data")
    if not isinstance(data, str) or not data:
        raise MtuWorkerContractError("MTU Worker text_mask 缺少数据")
    try:
        decoded = base64.b64decode(data, validate=True)
        image = Image.open(io.BytesIO(decoded)).convert("L")
    except Exception as error:
        raise MtuWorkerContractError("MTU Worker text_mask 不是有效 PNG") from error
    array = np.array(image)
    if array.shape != (expected_height, expected_width):
        raise MtuWorkerContractError(
            "MTU Worker text_mask 尺寸与输入图片不一致"
        )
    return array


def normalize_mtu_detect_response(
    payload: Mapping[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> Dict[str, Any]:
    """Convert a Worker response to Saber's existing detection result shape."""

    response = _require_mapping(payload, "detect 响应")
    _require_stage_response(response, "detect")
    regions = response.get("regions", [])
    if not isinstance(regions, list):
        raise MtuWorkerContractError("MTU Worker detect regions 必须是数组")

    result: Dict[str, Any] = {
        "coords": [],
        "polygons": [],
        "angles": [],
        "auto_directions": [],
        "textlines_per_bubble": [],
        "raw_mask": None,
    }
    for index, value in enumerate(regions):
        region = _require_mapping(value, f"detect regions[{index}]")
        coords = _coords(region.get("coords"), f"detect regions[{index}].coords")
        if coords[0] < 0 or coords[1] < 0 or coords[2] > image_width or coords[3] > image_height:
            raise MtuWorkerContractError(f"detect regions[{index}].coords 超出图片范围")
        polygon = region.get("polygon", [])
        textlines = region.get("textlines", [])
        if not isinstance(polygon, list) or not isinstance(textlines, list):
            raise MtuWorkerContractError(f"detect regions[{index}] 的 polygon/textlines 必须是数组")
        angle = _number(region.get("angle", 0), f"detect regions[{index}].angle")
        direction = str(region.get("direction", "") or "").strip().lower()
        if direction not in {"h", "v"}:
            direction = "v" if (coords[3] - coords[1]) > (coords[2] - coords[0]) else "h"
        result["coords"].append(coords)
        result["polygons"].append(polygon)
        result["angles"].append(angle)
        result["auto_directions"].append(direction)
        result["textlines_per_bubble"].append(textlines)

    if response.get("text_mask") is not None:
        result["raw_mask"] = _decode_mask(response["text_mask"], image_width, image_height)
    return result


def normalize_mtu_ocr_response(
    payload: Mapping[str, Any],
    *,
    expected_region_ids: Sequence[str],
) -> List[OcrResult]:
    """Return OCR values in request order and reject missing/unknown regions."""

    response = _require_mapping(payload, "ocr 响应")
    _require_stage_response(response, "ocr")
    values = response.get("results", [])
    if not isinstance(values, list):
        raise MtuWorkerContractError("MTU Worker ocr results 必须是数组")

    by_region: Dict[str, OcrResult] = {}
    expected = set(expected_region_ids)
    for index, value in enumerate(values):
        item = _require_mapping(value, f"ocr results[{index}]")
        region_id = item.get("id")
        if not isinstance(region_id, str) or not region_id:
            raise MtuWorkerContractError(f"ocr results[{index}] 缺少稳定区域 ID")
        if region_id not in expected or region_id in by_region:
            raise MtuWorkerContractError(f"ocr results[{index}] 包含未知或重复区域 ID: {region_id}")
        by_region[region_id] = OcrResult.from_dict(dict(item))

    missing = [region_id for region_id in expected_region_ids if region_id not in by_region]
    if missing:
        raise MtuWorkerContractError("MTU Worker OCR 缺少区域结果: " + ", ".join(missing))
    return [by_region[region_id] for region_id in expected_region_ids]
