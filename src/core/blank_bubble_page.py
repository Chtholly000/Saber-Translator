"""Compose a replaceable bubble-slot detector with the existing render port."""

from __future__ import annotations

from hashlib import sha256
import math
from pathlib import Path
from typing import Any, Mapping, Protocol

from PIL import Image

from src.core.blank_bubble_contract import (
    build_bubble_detect_request,
    normalize_bubble_detect_response,
)
from src.core.modal_worker_client import ModalWorkerClient


SLOT_DOCUMENT_VERSION = "blank-bubble-slots/v1"


class BubbleSlotDetector(Protocol):
    def detect(self, image: Image.Image) -> list[dict[str, Any]]: ...


class ModalMangaLensSlotDetector:
    """Use the pinned MTU MangaLens model, already installed on the image worker."""

    def __init__(self, worker_config: Mapping[str, Any], *, confidence=0.25, image_size=1600, client=None):
        if not isinstance(worker_config, Mapping) or not worker_config.get("app_name"):
            raise ValueError("缺少 Modal Worker app_name")
        self.client = client or ModalWorkerClient(**dict(worker_config))
        self.options = {"confidence": confidence, "image_size": image_size}

    def detect(self, image: Image.Image) -> list[dict[str, Any]]:
        request = build_bubble_detect_request(image, self.options)
        return normalize_bubble_detect_response(
            self.client.execute(request), image_size=image.size
        )


class HighContrastContourSlotDetector:
    """CPU alternative for clearly outlined, light interiors; no model or OCR."""

    def __init__(
        self,
        *,
        min_area_ratio: float = 0.0015,
        max_area_ratio: float = 0.15,
        min_fill_ratio: float = 0.62,
        min_dark_border: float = 0.65,
    ):
        if not 0 < min_area_ratio < max_area_ratio < 1:
            raise ValueError("轮廓区域比例无效")
        if (
            isinstance(min_dark_border, bool)
            or not isinstance(min_dark_border, (int, float))
            or not math.isfinite(min_dark_border)
            or not 0 <= min_dark_border <= 1
        ):
            raise ValueError("min_dark_border 必须是 0 到 1 的有限数字")
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio
        self.min_fill_ratio = min_fill_ratio
        self.min_dark_border = min_dark_border

    def detect(self, image: Image.Image) -> list[dict[str, Any]]:
        import cv2
        import numpy as np

        grayscale = np.asarray(image.convert("L"))
        height, width = grayscale.shape
        white = (grayscale >= 240).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        slots = []
        for component in range(1, count):
            x, y, box_width, box_height, area = map(int, stats[component])
            if x == 0 or y == 0 or x + box_width >= width or y + box_height >= height:
                continue
            if box_width < 40 or box_height < 40:
                continue
            area_ratio = area / (width * height)
            fill_ratio = area / (box_width * box_height)
            if not self.min_area_ratio <= area_ratio <= self.max_area_ratio:
                continue
            if fill_ratio < self.min_fill_ratio:
                continue
            left, top = max(0, x - 5), max(0, y - 5)
            right, bottom = min(width, x + box_width + 5), min(height, y + box_height + 5)
            component_mask = (labels[top:bottom, left:right] == component).astype(np.uint8)
            border = cv2.dilate(component_mask, kernel) - component_mask
            border_pixels = grayscale[top:bottom, left:right][border > 0]
            dark_border = float(np.mean(border_pixels < 110)) if border_pixels.size else 0.0
            if dark_border < self.min_dark_border:
                continue
            slots.append({
                "coords": [x, y, x + box_width, y + box_height],
                # Heuristic score, not a model probability.
                "confidence": round((fill_ratio + dark_border) / 2, 4),
            })
        return slots


class HybridBubbleSlotDetector:
    """Keep MTU's model detections, then add non-overlapping contour candidates."""

    def __init__(self, model: BubbleSlotDetector, contour: BubbleSlotDetector | None = None):
        self.model = model
        self.contour = contour or HighContrastContourSlotDetector()

    def detect(self, image: Image.Image) -> list[dict[str, Any]]:
        selected = list(self.model.detect(image))
        for candidate in self.contour.detect(image):
            x1, y1, x2, y2 = candidate["coords"]
            candidate_area = (x2 - x1) * (y2 - y1)
            duplicate = False
            for existing in selected:
                a1, b1, a2, b2 = existing["coords"]
                overlap = max(0, min(x2, a2) - max(x1, a1)) * max(0, min(y2, b2) - max(y1, b1))
                existing_area = (a2 - a1) * (b2 - b1)
                if overlap / min(candidate_area, existing_area) >= 0.65:
                    duplicate = True
                    break
            if not duplicate:
                selected.append(candidate)
        return selected


def make_slot_document(
    image: Image.Image,
    image_bytes: bytes,
    detector: BubbleSlotDetector,
    *,
    reading_order: str = "rtl",
    inset_ratio: float = 0.12,
) -> dict[str, Any]:
    if reading_order not in {"rtl", "ltr"}:
        raise ValueError("reading_order 必须是 rtl 或 ltr")
    if not 0 <= inset_ratio < 0.4:
        raise ValueError("inset_ratio 必须在 0 到 0.4 之间")
    regions = detector.detect(image)
    if not isinstance(regions, list) or len(regions) > 128:
        raise ValueError("气泡检测器必须返回区域列表")
    for region in regions:
        if not isinstance(region, Mapping):
            raise ValueError("气泡检测器返回了无效区域")
        coords = region.get("coords")
        confidence = region.get("confidence")
        if (
            not isinstance(coords, list) or len(coords) != 4
            or any(type(value) is not int for value in coords)
            or not (0 <= coords[0] < coords[2] <= image.width)
            or not (0 <= coords[1] < coords[3] <= image.height)
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("气泡检测器返回了无效坐标或置信度")
    # This is only a geometric heuristic. Explicit ID mapping and the saved
    # preview remain available when manga panel reading order is ambiguous.
    sorted_regions = sorted(
        regions,
        key=lambda item: (
            (item["coords"][1] + item["coords"][3]) / 2,
            -(item["coords"][0] + item["coords"][2]) / 2
            if reading_order == "rtl" else
            (item["coords"][0] + item["coords"][2]) / 2,
        ),
    )
    slots = []
    for index, region in enumerate(sorted_regions, start=1):
        x1, y1, x2, y2 = region["coords"]
        dx = max(2, round((x2 - x1) * inset_ratio))
        dy = max(2, round((y2 - y1) * inset_ratio))
        inner = [x1 + dx, y1 + dy, x2 - dx, y2 - dy]
        if inner[0] >= inner[2] or inner[1] >= inner[3]:
            raise ValueError(f"检测到的 slot-{index:04d} 过窄，无法放入文字")
        slots.append({
            "id": f"slot-{index:04d}",
            "coords": list(region["coords"]),
            "text_coords": inner,
            "confidence": float(region["confidence"]),
        })
    return {
        "schema": SLOT_DOCUMENT_VERSION,
        "image_sha256": sha256(image_bytes).hexdigest(),
        "image_width": image.width,
        "image_height": image.height,
        "reading_order": reading_order,
        "detector": type(detector).__name__,
        "slots": slots,
    }


def validate_slot_document(document: Any, image: Image.Image, image_bytes: bytes) -> list[dict]:
    if not isinstance(document, Mapping) or document.get("schema") != SLOT_DOCUMENT_VERSION:
        raise ValueError("空白气泡框文件版本无效")
    if (
        document.get("image_sha256") != sha256(image_bytes).hexdigest()
        or (document.get("image_width"), document.get("image_height")) != image.size
    ):
        raise ValueError("空白气泡框文件与当前图片不匹配")
    slots = document.get("slots")
    if not isinstance(slots, list) or len(slots) > 128:
        raise ValueError("空白气泡框文件 slots 无效")
    seen = set()
    for slot in slots:
        if not isinstance(slot, Mapping) or not isinstance(slot.get("id"), str) or slot["id"] in seen:
            raise ValueError("空白气泡框 ID 无效或重复")
        seen.add(slot["id"])
        for name in ("coords", "text_coords"):
            coords = slot.get(name)
            if (
                not isinstance(coords, list) or len(coords) != 4
                or any(type(value) is not int for value in coords)
                or not (0 <= coords[0] < coords[2] <= image.width)
                or not (0 <= coords[1] < coords[3] <= image.height)
            ):
                raise ValueError(f"{slot['id']} 的 {name} 无效")
        x1, y1, x2, y2 = slot["coords"]
        tx1, ty1, tx2, ty2 = slot["text_coords"]
        if not (x1 <= tx1 < tx2 <= x2 and y1 <= ty1 < ty2 <= y2):
            raise ValueError(f"{slot['id']} 的文字框不在气泡内")
        confidence = slot.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError(f"{slot['id']} 的置信度无效")
    return slots


def prepare_text_layout(
    slots: list[dict],
    supplied: Any,
    *,
    direction: str = "horizontal",
    font_family: str | None = None,
    font_size: int | None = None,
) -> dict[str, list[dict]]:
    if direction not in {"horizontal", "vertical"}:
        raise ValueError("文字方向必须是 horizontal 或 vertical")
    slot_ids = [slot["id"] for slot in slots]
    if isinstance(supplied, list):
        if len(supplied) != len(slot_ids):
            raise ValueError("文字数量与气泡框数量不一致")
        texts = dict(zip(slot_ids, supplied))
    elif isinstance(supplied, dict):
        if set(supplied) != set(slot_ids):
            raise ValueError("文字 ID 必须与气泡框 ID 完全一致")
        texts = supplied
    else:
        raise ValueError("文字必须是同序数组或按 slot ID 对应的对象")
    if any(not isinstance(value, str) for value in texts.values()):
        raise ValueError("每个气泡框的文字必须是字符串")
    if font_size is not None and (type(font_size) is not int or font_size <= 0):
        raise ValueError("font_size 必须是正整数")

    if font_family is None:
        from src.shared import constants

        font_family = constants.DEFAULT_FONT_RELATIVE_PATH
    if not isinstance(font_family, str) or not font_family.strip():
        raise ValueError("font_family 不能为空")

    states = []
    for slot in slots:
        ident = slot["id"]
        x1, y1, x2, y2 = slot["text_coords"]
        text = texts[ident]
        if font_size is None and text:
            from src.core.rendering import calculate_auto_font_size

            size = calculate_auto_font_size(
                text, x2 - x1, y2 - y1, direction, font_family,
                min_size=10, max_size=64, padding_ratio=0.9,
            )
        else:
            size = font_size or 26
        offset_y = 0
        if direction == "horizontal" and text:
            # The stock Saber renderer starts horizontal lines at the top of
            # the box. Center this new, supplied-text path using its existing
            # position port; leave the original translation path untouched.
            from src.core.rendering import get_font
            from src.shared import constants

            font = get_font(font_family, size)
            if font is None:
                raise ValueError(f"无法加载字体: {font_family}")
            max_width = x2 - x1
            line_count = 0
            for paragraph in text.split("\n"):
                current_width = 0
                if paragraph:
                    line_count += 1
                for char in paragraph:
                    bounds = font.getbbox(char)
                    char_width = bounds[2] - bounds[0]
                    if current_width and current_width + char_width > max_width:
                        line_count += 1
                        current_width = 0
                    current_width += char_width
            line_height = int(size * constants.DEFAULT_LINE_SPACING) + 5
            text_height = max(size, (line_count - 1) * line_height + size)
            offset_y = max(0, ((y2 - y1) - text_height) // 2)
        states.append({
            "bubbleId": ident,
            "coords": [x1, y1, x2, y2],
            "translatedText": text,
            "fontFamily": font_family,
            "fontSize": size,
            "textDirection": direction,
            "strokeEnabled": False,
            "textAlign": "center",
            "position": {"x": 0, "y": offset_y},
        })
    return {"bubble_states": states}


def render_supplied_text(image: Image.Image, layout: dict, *, profile: str = "local_saber") -> Image.Image:
    from tools.typeset import typeset

    return typeset(image, layout, profile=profile)


def read_source_image(path: Path) -> tuple[Image.Image, bytes]:
    image_bytes = path.read_bytes()
    with Image.open(path) as source:
        return source.convert("RGB"), image_bytes
