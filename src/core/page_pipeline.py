"""UI-neutral full-page manga translation pipeline.

The controller owns stage order only. Every implementation is resolved from a
configured pipeline profile and the independent stage registries; no Flask,
Vue, Modal, MTU, or provider-specific code belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Dict, List, Mapping, Optional
from uuid import uuid4

import numpy as np
from PIL import Image

from src.core.config_models import BubbleState, BubbleTextline
from src.core.local_stage_handlers import (
    calculate_auto_font_size,
    extract_bubble_colors,
    get_bubble_detection_result_with_auto_directions,
    inpaint_bubbles,
    recognize_ocr_results_in_bubbles,
    render_bubbles_unified,
    translate_text_list,
)
from src.core.ocr_types import OcrResult
from src.core.pipeline_profiles import get_pipeline_profile
from src.core.stage_backends import create_stage_backend
from src.shared import constants


_LOCAL_HANDLERS = {
    "detect": get_bubble_detection_result_with_auto_directions,
    "ocr": recognize_ocr_results_in_bubbles,
    "color": extract_bubble_colors,
    "translate": translate_text_list,
    "inpaint": inpaint_bubbles,
    "render": render_bubbles_unified,
}


@dataclass(frozen=True)
class PageStyle:
    font_size: int = constants.DEFAULT_FONT_SIZE
    font_family: str = constants.DEFAULT_FONT_RELATIVE_PATH
    text_direction: str = "auto"
    text_color: str = constants.DEFAULT_TEXT_COLOR
    fill_color: str = constants.DEFAULT_FILL_COLOR
    stroke_enabled: bool = constants.DEFAULT_STROKE_ENABLED
    stroke_color: str = constants.DEFAULT_STROKE_COLOR
    stroke_width: int = constants.DEFAULT_STROKE_WIDTH
    line_spacing: float = constants.DEFAULT_LINE_SPACING
    text_align: str = constants.DEFAULT_TEXT_ALIGN


@dataclass
class PagePipelineOptions:
    source_language: str = "japanese"
    target_language: str = "Simplified Chinese"
    prompt_content: Optional[str] = None
    inpaint_method: str = "lama_mpe"
    # Match the established browser defaults so headless runs do not silently
    # use a tighter, lower-quality repair mask.
    mask_dilate_size: int = 10
    mask_box_expand_ratio: float = 20
    auto_font_size: bool = True
    extract_colors: bool = True
    style: PageStyle = field(default_factory=PageStyle)
    detect_options: Dict[str, Any] = field(default_factory=dict)
    ocr_options: Dict[str, Any] = field(default_factory=dict)
    translate_options: Dict[str, Any] = field(default_factory=dict)
    inpaint_options: Dict[str, Any] = field(default_factory=dict)
    render_options: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageRun:
    stage: str
    backend: str
    duration_ms: float
    skipped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "backend": self.backend,
            "durationMs": self.duration_ms,
            "skipped": self.skipped,
        }


@dataclass
class PagePipelineResult:
    profile: str
    clean_image: Image.Image
    final_image: Image.Image
    bubble_states: List[BubbleState]
    stage_runs: List[StageRun]

    def to_document(self, *, artifacts: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        return {
            "bubbleStateContractVersion": 1,
            "pipelineProfile": self.profile,
            "stageBackends": {run.stage: run.backend for run in self.stage_runs},
            "stageRuns": [run.to_dict() for run in self.stage_runs],
            "artifacts": dict(artifacts or {}),
            "bubble_states": [state.to_dict() for state in self.bubble_states],
        }


def _direction(value: Any) -> str:
    return "vertical" if str(value or "").lower() in {"v", "vertical"} else "horizontal"


def _rgb(value: Any) -> Optional[tuple[int, int, int]]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    channels = tuple(int(channel) for channel in value)
    if any(channel < 0 or channel > 255 for channel in channels):
        return None
    return channels


def _hex(value: Optional[tuple[int, int, int]], fallback: str) -> str:
    return fallback if value is None else "#{:02x}{:02x}{:02x}".format(*value)


def _normalized_coords(values: Any, image: Image.Image) -> List[tuple[int, int, int, int]]:
    if not isinstance(values, list):
        raise ValueError("检测结果 coords 必须是数组")
    coords = []
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            raise ValueError("检测框必须包含四个坐标")
        box = tuple(int(round(number)) for number in value)
        if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
            raise ValueError("检测框超出图片范围或宽高无效")
        coords.append(box)
    return coords


def _aligned(values: Any, count: int, name: str, default: Any) -> List[Any]:
    if values is None:
        return [default() if callable(default) else default for _ in range(count)]
    if not isinstance(values, list) or len(values) != count:
        raise ValueError(f"检测结果 {name} 数量与区域不一致")
    return values


def run_page_pipeline(
    image: Image.Image,
    *,
    profile: str,
    options: Optional[PagePipelineOptions] = None,
) -> PagePipelineResult:
    """Run detect → OCR → color → translate → inpaint → render without a UI."""
    options = options or PagePipelineOptions()
    if options.inpaint_method not in {"solid", "lama_mpe", "litelama"}:
        raise ValueError("inpaint_method 必须是 solid/lama_mpe/litelama")
    if not 0 <= options.mask_dilate_size <= 128:
        raise ValueError("mask_dilate_size 必须在 0–128 之间")
    if not 0 <= options.mask_box_expand_ratio <= 100:
        raise ValueError("mask_box_expand_ratio 必须在 0–100 之间")
    if options.style.text_direction not in {"auto", "vertical", "horizontal"}:
        raise ValueError("text_direction 必须是 auto/vertical/horizontal")
    if not isinstance(image, Image.Image) or image.width <= 0 or image.height <= 0:
        raise ValueError("输入必须是非空 PIL 图片")

    source = image.convert("RGB").copy()
    pipeline_profile = get_pipeline_profile(profile)
    backends = {}
    backend_names = {}
    for stage, local_handler in _LOCAL_HANDLERS.items():
        name = pipeline_profile.backend_for(stage)
        backend_names[stage] = name
        backends[stage] = create_stage_backend(stage, name, local_handler=local_handler)

    runs: List[StageRun] = []

    def execute(stage: str, *args: Any, **kwargs: Any) -> Any:
        started = perf_counter()
        result = backends[stage].execute(*args, **kwargs)
        runs.append(StageRun(stage, backend_names[stage], round((perf_counter() - started) * 1000, 3)))
        return result

    detection = execute("detect", source, **dict(options.detect_options))
    if not isinstance(detection, dict):
        raise ValueError("检测阶段必须返回对象")
    coords = _normalized_coords(detection.get("coords"), source)
    count = len(coords)
    polygons = _aligned(detection.get("polygons"), count, "polygons", list)
    angles = _aligned(detection.get("angles"), count, "angles", 0)
    auto_directions = _aligned(detection.get("auto_directions"), count, "auto_directions", "h")
    textlines = _aligned(detection.get("textlines_per_bubble"), count, "textlines_per_bubble", list)

    if count:
        ocr_kwargs = dict(options.ocr_options)
        ocr_kwargs.update(source_language=options.source_language, textlines_per_bubble=textlines)
        ocr_results = execute("ocr", source, coords, **ocr_kwargs)
    else:
        ocr_results = []
        runs.append(StageRun("ocr", backend_names["ocr"], 0.0, skipped=True))
    if not isinstance(ocr_results, list) or len(ocr_results) != count or \
            any(not isinstance(result, OcrResult) for result in ocr_results):
        raise ValueError("OCR 结果数量或类型与检测区域不一致")

    if count and options.extract_colors:
        colors = execute("color", source, coords, textlines_per_bubble=textlines)
        if not isinstance(colors, list) or len(colors) != count:
            raise ValueError("颜色结果数量与检测区域不一致")
    else:
        colors = [{} for _ in range(count)]
        runs.append(StageRun("color", backend_names["color"], 0.0, skipped=True))

    originals = [result.text for result in ocr_results]
    if count:
        translate_kwargs = dict(options.translate_options)
        translate_kwargs.update(
            target_language=options.target_language,
            prompt_content=options.prompt_content,
        )
        translations = execute("translate", originals, **translate_kwargs)
    else:
        translations = []
        runs.append(StageRun("translate", backend_names["translate"], 0.0, skipped=True))
    if not isinstance(translations, list) or len(translations) != count or \
            any(not isinstance(value, str) for value in translations):
        raise ValueError("翻译结果数量或类型与 OCR 结果不一致")

    states: List[BubbleState] = []
    for index, coord in enumerate(coords):
        color = colors[index] if isinstance(colors[index], dict) else {}
        foreground, background = _rgb(color.get("fg_color")), _rgb(color.get("bg_color"))
        automatic_direction = _direction(auto_directions[index])
        selected_direction = (
            automatic_direction if options.style.text_direction == "auto"
            else options.style.text_direction
        )
        line_values = textlines[index] if isinstance(textlines[index], list) else []
        polygon = polygons[index] if isinstance(polygons[index], list) else []
        states.append(BubbleState(
            bubble_id=str(uuid4()),
            original_text=originals[index],
            translated_text=translations[index],
            coords=coord,
            polygon=[[int(point[0]), int(point[1])] for point in polygon
                     if isinstance(point, (list, tuple)) and len(point) >= 2],
            font_size=options.style.font_size,
            font_family=options.style.font_family,
            text_direction=selected_direction,
            auto_text_direction=automatic_direction,
            text_color=_hex(foreground, options.style.text_color),
            fill_color=_hex(background, options.style.fill_color),
            rotation_angle=float(angles[index] or 0),
            stroke_enabled=options.style.stroke_enabled,
            stroke_color=options.style.stroke_color,
            stroke_width=options.style.stroke_width,
            line_spacing=options.style.line_spacing,
            text_align=options.style.text_align,
            inpaint_method=options.inpaint_method,
            auto_fg_color=foreground,
            auto_bg_color=background,
            color_confidence=float(color.get("confidence", 0) or 0),
            textlines=[BubbleTextline.from_dict(value) for value in line_values
                       if isinstance(value, dict)],
            ocr_result=ocr_results[index],
        ))

    inpaint_kwargs = dict(options.inpaint_options)
    inpaint_kwargs.update(
        method="solid" if options.inpaint_method == "solid" else "lama",
        fill_color=options.style.fill_color,
        bubble_polygons=polygons,
        precise_mask=detection.get("raw_mask"),
        mask_dilate_size=options.mask_dilate_size,
        mask_box_expand_ratio=options.mask_box_expand_ratio,
        lama_model=("litelama" if options.inpaint_method == "litelama" else "lama_mpe"),
    )
    clean_image, _ = execute("inpaint", source, coords, **inpaint_kwargs)
    if not isinstance(clean_image, Image.Image) or clean_image.size != source.size:
        raise ValueError("修复结果必须是与原图同尺寸的 PIL 图片")
    clean_image = clean_image.convert("RGB")

    render_kwargs = dict(options.render_options)
    if backend_names["render"] == "local":
        if options.auto_font_size:
            for state in states:
                if state.translated_text:
                    x1, y1, x2, y2 = state.coords
                    state.font_size = calculate_auto_font_size(
                        state.translated_text,
                        x2 - x1,
                        y2 - y1,
                        state.text_direction,
                        state.font_family,
                    )
        final_image = execute("render", clean_image.copy(), states, **render_kwargs)
    else:
        render_kwargs["auto_font_size"] = options.auto_font_size
        final_image = execute("render", clean_image.copy(), states, **render_kwargs)
    if not isinstance(final_image, Image.Image) or final_image.size != source.size:
        raise ValueError("渲染结果必须是与原图同尺寸的 PIL 图片")

    return PagePipelineResult(
        profile=pipeline_profile.name,
        clean_image=clean_image,
        final_image=final_image.convert("RGB"),
        bubble_states=states,
        stage_runs=runs,
    )
