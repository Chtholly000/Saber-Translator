"""Agent-facing native MTU page client; no browser or editor is required."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from PIL import Image

from src.core.native_mtu_page_contract import (
    DEFAULT_NATIVE_MTU_GPU_BATCH_PAGES,
    MAX_NATIVE_MTU_BATCH_PAGES,
)
from src.core.native_page_bootstrap import configure_native_mtu_page_engine
from src.core.page_engines import create_page_engine


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        required=True,
        action="append",
        type=Path,
        help="Input page; repeat --image to process a batch",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Non-secret native worker and MTU module configuration",
    )
    parser.add_argument(
        "--gpu-batch-size",
        type=int,
        default=DEFAULT_NATIVE_MTU_GPU_BATCH_PAGES,
        help=(
            "Pages per Modal extract/render call "
            f"(1-{MAX_NATIVE_MTU_BATCH_PAGES}; "
            f"default: {DEFAULT_NATIVE_MTU_GPU_BATCH_PAGES})"
        ),
    )
    args = parser.parse_args()

    missing = [str(path) for path in args.image if not path.is_file()]
    if missing:
        parser.error("输入图片不存在: " + ", ".join(missing))
    if not args.config.is_file():
        parser.error("配置文件不存在")
    if not 1 <= args.gpu_batch_size <= MAX_NATIVE_MTU_BATCH_PAGES:
        parser.error(
            "--gpu-batch-size 必须在 1 到 "
            f"{MAX_NATIVE_MTU_BATCH_PAGES} 之间"
        )
    if args.output_dir.exists():
        parser.error("输出目录已存在，请选择新目录")
    if not args.output_dir.parent.is_dir():
        parser.error("输出目录的父目录不存在")

    configure_native_mtu_page_engine(_load_json(args.config))
    engine = create_page_engine("mtu_native")
    try:
        engine.check_ready()
    except ValueError as exc:
        parser.error(str(exc))
    sources = []
    for path in args.image:
        with Image.open(path) as source:
            sources.append(source.convert("RGB"))
    if len(sources) == 1:
        results = [engine.execute(sources[0])]
    else:
        results = engine.execute_batch(
            sources,
            gpu_batch_size=args.gpu_batch_size,
        )

    temporary = Path(
        tempfile.mkdtemp(prefix=".saber-native-page-", dir=args.output_dir.parent)
    )
    try:
        batch_records = []
        for index, (path, result) in enumerate(zip(args.image, results), start=1):
            target = temporary if len(results) == 1 else temporary / f"page-{index:04d}"
            if len(results) > 1:
                target.mkdir()
            result.clean_image.save(target / "clean.png", format="PNG")
            result.final_image.save(target / "final.png", format="PNG")
            if result.repair_mask is not None:
                result.repair_mask.save(target / "mask.png", format="PNG")
            document = result.to_document(artifacts={
                "clean": "clean.png",
                "rendered": "final.png",
                "repairMask": "mask.png",
            })
            with (target / "page.json").open("x", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
            batch_records.append({
                "page": index,
                "sourceName": path.name,
                "output": "." if len(results) == 1 else target.name,
                "regionCount": result.metadata.get("regionCount", 0),
            })
        if len(results) > 1:
            with (temporary / "batch.json").open("x", encoding="utf-8") as handle:
                json.dump({
                    "pageEngineBatchContractVersion": 1,
                    "pageEngine": "mtu_native",
                    "gpuBatchSize": args.gpu_batch_size,
                    "pages": batch_records,
                }, handle, ensure_ascii=False, indent=2)
        temporary.replace(args.output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    print(json.dumps({
        "output_dir": str(args.output_dir),
        "engine": results[0].engine,
        "page_count": len(results),
        "region_count": sum(
            len(result.native_document.get("regions", [])) for result in results
        ),
        "gpu_batch_size": args.gpu_batch_size if len(results) > 1 else 1,
        "mtu_revision": results[0].metadata.get("mtuRevision"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
