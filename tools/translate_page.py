"""Headless full pipeline: image -> clean PNG, translated PNG, BubbleState JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image

from src.core.page_pipeline import PagePipelineOptions, PageStyle, run_page_pipeline
from src.core.pipeline_plugins import configure_pipeline_plugins
from src.core.remote_bootstrap import configure_remote_backends


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--config", type=Path, help="Non-secret remote backend configuration")
    parser.add_argument("--plugins-config", type=Path, help="Trusted stage plugin configuration")
    parser.add_argument("--source-language", default="japanese")
    parser.add_argument("--target-language", default="Simplified Chinese")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--inpaint-method", choices=("solid", "lama_mpe", "litelama"), default="lama_mpe")
    defaults = PagePipelineOptions()
    parser.add_argument("--mask-dilate-size", type=int, default=defaults.mask_dilate_size)
    parser.add_argument("--mask-box-expand-ratio", type=float, default=defaults.mask_box_expand_ratio)
    parser.add_argument("--font-family", default=PageStyle().font_family)
    parser.add_argument("--font-size", type=int, default=PageStyle().font_size)
    parser.add_argument("--text-direction", choices=("auto", "vertical", "horizontal"), default="auto")
    parser.add_argument("--no-auto-font-size", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    if not args.image.is_file():
        parser.error("输入图片不存在")
    if args.output_dir.exists():
        parser.error("输出目录已存在，请选择新目录")
    if not args.output_dir.parent.is_dir():
        parser.error("输出目录的父目录不存在")
    if not 0 <= args.mask_dilate_size <= 128 or not 0 <= args.mask_box_expand_ratio <= 100:
        parser.error("mask 参数超出范围")

    if args.config:
        configure_remote_backends(_load_json(args.config))
    installation = None
    try:
        if args.plugins_config:
            installation = configure_pipeline_plugins(_load_json(args.plugins_config))
        prompt = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else None
        options = PagePipelineOptions(
            source_language=args.source_language,
            target_language=args.target_language,
            prompt_content=prompt,
            inpaint_method=args.inpaint_method,
            mask_dilate_size=args.mask_dilate_size,
            mask_box_expand_ratio=args.mask_box_expand_ratio,
            auto_font_size=not args.no_auto_font_size,
            extract_colors=not args.no_color,
            style=PageStyle(
                font_size=args.font_size,
                font_family=args.font_family,
                text_direction=args.text_direction,
            ),
        )
        with Image.open(args.image) as image:
            result = run_page_pipeline(image, profile=args.profile, options=options)

        temporary = Path(tempfile.mkdtemp(prefix=".saber-page-", dir=args.output_dir.parent))
        try:
            result.clean_image.save(temporary / "clean.png", format="PNG")
            result.final_image.save(temporary / "final.png", format="PNG")
            document = result.to_document(artifacts={
                "clean": "clean.png",
                "rendered": "final.png",
            })
            with (temporary / "page.json").open("x", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
            temporary.replace(args.output_dir)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    finally:
        if installation:
            installation.close()

    print(json.dumps({
        "output_dir": str(args.output_dir),
        "profile": result.profile,
        "bubble_count": len(result.bubble_states),
        "stage_runs": [run.to_dict() for run in result.stage_runs],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
