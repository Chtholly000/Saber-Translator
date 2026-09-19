"""Headless typesetting client: image + BubbleState JSON -> PNG, no OCR/LLM."""

import argparse
import json
from pathlib import Path

from PIL import Image

from src.core.config_models import BubbleState
from src.core.local_stage_handlers import render_bubbles_unified
from src.core.pipeline_profiles import resolve_stage_backend
from src.core.stage_backends import create_stage_backend


def typeset(image, layout, *, profile="local_saber"):
    values = layout.get("bubble_states") if isinstance(layout, dict) else layout
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        raise ValueError("layout 必须为 BubbleState 数组或含 bubble_states 的对象")
    states = [BubbleState.from_dict(value) for value in values]
    for state in states:
        x1, y1, x2, y2 = state.coords
        if not (0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height):
            raise ValueError("文字框必须在图片范围内且宽高大于零")
    _, backend_name = resolve_stage_backend(profile, "render")
    renderer = create_stage_backend("render", backend_name, local_handler=render_bubbles_unified)
    return renderer.execute(image.convert("RGB"), states)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("输出文件已存在，请选择新路径")
    with args.layout.open(encoding="utf-8") as handle:
        layout = json.load(handle)
    with Image.open(args.image) as image:
        output = typeset(image, layout)
    with args.output.open("xb") as handle:
        output.save(handle, format="PNG")


if __name__ == "__main__":
    main()
