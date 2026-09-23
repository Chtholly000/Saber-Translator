"""Detect empty manga balloons and place supplied text; no OCR or translator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from PIL import ImageDraw, ImageFont

from src.core.blank_bubble_page import (
    HighContrastContourSlotDetector,
    HybridBubbleSlotDetector,
    ModalMangaLensSlotDetector,
    make_slot_document,
    prepare_text_layout,
    read_source_image,
    render_supplied_text,
    validate_slot_document,
)


def _read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _preview(image, slots):
    preview = image.copy()
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default()
    for slot in slots:
        draw.rectangle(slot["coords"], outline="#ff2d55", width=3)
        draw.rectangle(slot["text_coords"], outline="#0066ff", width=2)
        x1, y1, _, _ = slot["coords"]
        draw.text((x1, max(0, y1 - 14)), slot["id"], fill="#d00036", font=font)
    return preview


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Non-secret native Worker configuration; required unless --slots is supplied")
    parser.add_argument("--slots", type=Path, help="Reuse a saved slots.json without another GPU call")
    parser.add_argument("--texts", type=Path, help="JSON array in reading order, or object keyed by slot ID")
    parser.add_argument("--select-slot", action="append", help="Use only this detected slot ID; repeat for multiple slots")
    parser.add_argument("--detector", choices=("mangalens", "contour", "hybrid"), default="mangalens")
    parser.add_argument("--reading-order", choices=("rtl", "ltr"), default="rtl")
    parser.add_argument("--direction", choices=("horizontal", "vertical"), default="horizontal")
    parser.add_argument("--inset-ratio", type=float, default=0.12)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--image-size", type=int, default=1600)
    parser.add_argument("--font-family")
    parser.add_argument("--font-size", type=int)
    parser.add_argument("--render-profile", default="local_saber")
    args = parser.parse_args()

    if not args.image.is_file():
        parser.error("图片不存在")
    if args.output_dir.exists() or not args.output_dir.parent.is_dir():
        parser.error("输出目录必须不存在，且父目录必须存在")
    if not args.slots and args.detector in {"mangalens", "hybrid"} and not args.config:
        parser.error("MangaLens 检测需要 --config；轮廓模式可直接使用 --detector contour")
    if args.slots and not args.slots.is_file():
        parser.error("slots 文件不存在")
    if args.texts and not args.texts.is_file():
        parser.error("文字文件不存在")

    image, image_bytes = read_source_image(args.image)
    if args.slots:
        document = _read_json(args.slots)
        slots = validate_slot_document(document, image, image_bytes)
    else:
        if args.detector == "contour":
            detector = HighContrastContourSlotDetector()
        else:
            config = _read_json(args.config)
            model = ModalMangaLensSlotDetector(
                config.get("worker", {}),
                confidence=args.confidence,
                image_size=args.image_size,
            )
            detector = model if args.detector == "mangalens" else HybridBubbleSlotDetector(model)
        document = make_slot_document(
            image, image_bytes, detector,
            reading_order=args.reading_order,
            inset_ratio=args.inset_ratio,
        )
        slots = validate_slot_document(document, image, image_bytes)

    if not slots:
        raise ValueError("未检测到气泡框；未写出图片，请检查原图或更换检测模型")

    selected = slots
    if args.select_slot:
        requested = args.select_slot
        available = {slot["id"] for slot in slots}
        if len(set(requested)) != len(requested) or not set(requested) <= available:
            raise ValueError("所选气泡框 ID 重复或不存在")
        selected = [slot for slot in slots if slot["id"] in set(requested)]

    layout = None
    final_image = None
    if args.texts:
        layout = prepare_text_layout(
            selected, _read_json(args.texts),
            direction=args.direction,
            font_family=args.font_family,
            font_size=args.font_size,
        )
        final_image = render_supplied_text(image, layout, profile=args.render_profile)

    temporary = Path(tempfile.mkdtemp(prefix=".saber-blank-page-", dir=args.output_dir.parent))
    try:
        (temporary / "slots.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _preview(image, slots).save(temporary / "slots-preview.png", format="PNG")
        if final_image is not None:
            final_image.save(temporary / "final.png", format="PNG")
            (temporary / "layout.json").write_text(
                json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        temporary.replace(args.output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(json.dumps({
        "output_dir": str(args.output_dir),
        "slot_count": len(slots),
        "selected_count": len(selected),
        "rendered": final_image is not None,
        "detector": document.get("detector"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
