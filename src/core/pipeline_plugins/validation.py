"""Validate plugin outputs before they enter a route or headless client."""

import math
from numbers import Real

from PIL import Image

from src.core.ocr_types import OcrResult


def _require(condition, stage):
    if not condition:
        raise ValueError(f"阶段插件输出不符合 {stage} 契约；结果未写回，请核对 STAGE_PLUGINS.md")


def _finite(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _image(value, source, stage):
    _require(isinstance(value, Image.Image) and value.size == source.size
             and value.mode in {"RGB", "RGBA"}, stage)


def validate_result(stage, result, args):
    if stage == "detect":
        _require(isinstance(result, dict) and isinstance(result.get("coords"), list), stage)
        coords = result["coords"]
        width, height = args[0].size
        for box in coords:
            _require(isinstance(box, (list, tuple)) and len(box) == 4 and all(_finite(v) for v in box), stage)
            _require(0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height, stage)
        for key in ("angles", "polygons", "auto_directions", "textlines_per_bubble"):
            if key in result:
                _require(isinstance(result[key], list) and len(result[key]) == len(coords), stage)
        if result.get("raw_mask") is not None:
            import numpy as np
            mask = result["raw_mask"]
            _require(isinstance(mask, np.ndarray) and mask.shape == (height, width) and mask.dtype == np.uint8, stage)
    elif stage == "ocr":
        _require(isinstance(result, list) and len(result) == len(args[1]), stage)
        for value in result:
            _require(isinstance(value, OcrResult) and isinstance(value.text, str), stage)
            _require(value.confidence is None or (_finite(value.confidence) and 0 <= value.confidence <= 1), stage)
    elif stage == "color":
        _require(isinstance(result, list) and len(result) == len(args[1]), stage)
        for value in result:
            _require(isinstance(value, dict) and {"fg_color", "bg_color"} <= set(value), stage)
            for channel in ("fg_color", "bg_color"):
                color = value[channel]
                _require(color is None or (isinstance(color, (list, tuple)) and len(color) == 3
                         and all(type(v) is int and 0 <= v <= 255 for v in color)), stage)
    elif stage == "translate":
        _require(isinstance(result, list) and len(result) == len(args[0])
                 and all(isinstance(value, str) for value in result), stage)
    elif stage == "inpaint":
        _require(isinstance(result, tuple) and len(result) == 2, stage)
        _image(result[0], args[0], stage)
        if result[1] is not None:
            _image(result[1], args[0], stage)
    elif stage == "render":
        _image(result, args[0], stage)
