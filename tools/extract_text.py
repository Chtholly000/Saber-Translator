"""Headless detect/OCR client; emits editable BubbleState JSON without translation."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from PIL import Image

from src.core.stage_backends import create_stage_backend
from src.core.local_stage_handlers import (
    get_bubble_detection_result_with_auto_directions, recognize_ocr_results_in_bubbles,
)
from src.core.pipeline_profiles import resolve_stage_backend
from src.core.remote_bootstrap import configure_remote_backends
from src.core.pipeline_plugins import configure_pipeline_plugins


def extract_text(image, *, profile="local_saber"):
    def backend(stage):
        _, name = resolve_stage_backend(profile, stage)
        return create_stage_backend(stage, name, local_handler=(
            get_bubble_detection_result_with_auto_directions if stage == "detect"
            else recognize_ocr_results_in_bubbles))
    result = backend("detect").execute(image)
    coords = result["coords"]
    recognized = backend("ocr").execute(image, coords, textlines_per_bubble=result.get("textlines_per_bubble", [])) if coords else []
    if len(recognized) != len(coords):
        raise ValueError("OCR 区域数量不匹配")
    return {"bubbleStateContractVersion": 1, "pipelineProfile": profile,
            "bubble_states": [{"bubbleId": str(uuid4()), "coords": coord,
                               "originalText": recognized[index].text, "translatedText": "",
                               "ocrResult": recognized[index].to_dict(),
                               "polygon": result.get("polygons", [[]] * len(coords))[index],
                               "rotationAngle": result.get("angles", [0] * len(coords))[index],
                               "textlines": result.get("textlines_per_bubble", [[]] * len(coords))[index]}
                              for index, coord in enumerate(coords)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path, help="Optional non-secret Modal configuration")
    parser.add_argument("--plugins-config", type=Path, help="Stage plugin configuration")
    parser.add_argument("--profile", help="Explicit configured pipeline profile")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("输出文件已存在，请选择新路径")
    profile = "local_saber"
    if args.config:
        with args.config.open(encoding="utf-8") as handle:
            configure_remote_backends(json.load(handle))
        profile = "modal_mtu_deepseek"
    installation = None
    try:
        if args.plugins_config:
            with args.plugins_config.open(encoding="utf-8") as handle:
                installation = configure_pipeline_plugins(json.load(handle))
        with Image.open(args.image) as image:
            document = extract_text(image.convert("RGB"), profile=args.profile or profile)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
    finally:
        if installation:
            installation.close()


if __name__ == "__main__":
    main()
