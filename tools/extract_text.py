"""Headless detect/OCR client; emits editable BubbleState JSON without translation."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from PIL import Image

from src.core.extraction_backends import create_extraction_backend
from src.core.local_stage_handlers import (
    get_bubble_detection_result_with_auto_directions, recognize_ocr_results_in_bubbles,
)
from src.core.pipeline_profiles import resolve_stage_backend
from src.core.remote_bootstrap import configure_remote_backends


def extract_text(image, *, profile="local_saber"):
    def backend(stage):
        _, name = resolve_stage_backend(profile, stage)
        return create_extraction_backend(name,
            local_detect=get_bubble_detection_result_with_auto_directions,
            local_ocr=recognize_ocr_results_in_bubbles)
    result = backend("detect").detect(image)
    coords = result["coords"]
    recognized = backend("ocr").ocr(image, coords, textlines_per_bubble=result.get("textlines_per_bubble", [])) if coords else []
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
    args = parser.parse_args()
    if args.output.exists():
        parser.error("输出文件已存在，请选择新路径")
    profile = "local_saber"
    if args.config:
        with args.config.open(encoding="utf-8") as handle:
            configure_remote_backends(json.load(handle))
        profile = "modal_mtu_deepseek"
    with Image.open(args.image) as image:
        document = extract_text(image.convert("RGB"), profile=profile)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
