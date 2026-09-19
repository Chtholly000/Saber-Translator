"""Versioned Worker dispatcher and the pinned MTU stage bindings.

Importing this file does not import MTU, load weights or establish a connection.
The injected bindings are also the seam used by deterministic offline fixtures.
"""

from types import SimpleNamespace

import numpy as np
from PIL import Image

from src.core.mtu_worker_contract import (
    MTU_WORKER_CONTRACT_VERSION, MTU_MODEL_OPTION_KEYS, MtuWorkerContractError, _coords,
    decode_worker_png, encode_worker_png,
)

MTU_REVISION = "f0307a063214f915f2b1d6e5cd3233f3bf78339f"

OPTION_KEYS = MTU_MODEL_OPTION_KEYS


def polygon_points(value, width, height):
    points = np.asarray(value, dtype=float)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise MtuWorkerContractError("文本行必须有四个有限坐标点")
    if (points < 0).any() or (points[:, 0] > width).any() or (points[:, 1] > height).any():
        raise MtuWorkerContractError("文本行坐标超出图片")
    if np.ptp(points[:, 0]) <= 0 or np.ptp(points[:, 1]) <= 0:
        raise MtuWorkerContractError("文本行区域不能为空")
    return points.astype(np.float32)


class PinnedMtuEngine:
    def __init__(self, *, device="cuda", bindings=None):
        self.device = device
        self._bindings = bindings

    def bindings(self):
        if self._bindings is None:
            from manga_translator import config
            from manga_translator.detection import dispatch as detect
            from manga_translator.ocr import dispatch as ocr
            from manga_translator.inpainting import dispatch as inpaint
            from manga_translator.textline_merge import dispatch as merge
            from manga_translator.utils import Quadrilateral
            self._bindings = SimpleNamespace(config=config, detect=detect, ocr=ocr,
                                             inpaint=inpaint, merge=merge, quad=Quadrilateral)
        return self._bindings

    async def detect(self, image, options):
        b = self.bindings()
        config = b.config.Config()
        config.detector = b.config.DetectorConfig(**options)
        d = config.detector
        lines, mask, _ = await b.detect(
            d.detector, np.array(image), d.detection_size, d.text_threshold,
            d.box_threshold, d.unclip_ratio, device=self.device, verbose=False,
            min_box_area_ratio=d.min_box_area_ratio,
        )
        # MTU's merger groups textlines into blocks; no OCR or whole controller.
        for line in lines:
            line.clip(image.width, image.height)
        blocks = await b.merge(lines, image.width, image.height, config) if lines else []
        regions = []
        for index, block in enumerate(blocks):
            coords = np.asarray(block.xyxy).round().astype(int).tolist()
            direction = "v" if block.direction.startswith("v") else "h"
            # TextBlock.min_rect supplies the rotated outer quadrilateral.
            polygon = np.asarray(block.min_rect).reshape(4, 2)
            polygon[:, 0] = polygon[:, 0].clip(0, image.width)
            polygon[:, 1] = polygon[:, 1].clip(0, image.height)
            regions.append({"id": f"region-{index}", "coords": coords,
                            "polygon": polygon.tolist(), "angle": float(block.angle),
                            "direction": direction,
                            "textlines": [{"polygon": np.asarray(line).tolist(), "direction": direction}
                                          for line in block.lines]})
        result = {"regions": regions}
        if mask is not None:
            pixels = np.asarray(mask)
            if pixels.ndim == 3:
                pixels = pixels[:, :, 0]
            if pixels.shape != (image.height, image.width):
                raise MtuWorkerContractError("MTU detector mask 不在原图坐标空间")
            if pixels.size and pixels.max() <= 1:
                pixels = pixels * 255
            result["text_mask"] = encode_worker_png(Image.fromarray(pixels.astype(np.uint8)))
        return result

    async def recognize(self, image, regions, options, *, colors=False):
        b = self.bindings()
        engine = "48px" if colors else options.get("ocr", "48px")
        # API-based OCR remains outside GPU workers; model additions are explicit.
        if engine not in {"32px", "48px", "48px_ctc", "mocr"}:
            raise MtuWorkerContractError("该 MTU OCR 模型尚未适配")
        config = b.config.OcrConfig(ocr=b.config.Ocr(engine), prob=0.0,
                                   ignore_bubble=0, use_model_bubble_filter=False)
        results = []
        for region in regions:
            x1, y1, x2, y2 = region["coords"]
            lines = region.get("textlines") or [{"polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}]
            quads = []
            for line in lines:
                points = polygon_points(line["polygon"], image.width, image.height)
                quad = b.quad(points, "", 1.0)
                if line.get("direction") in {"h", "v"}:
                    quad.assigned_direction = line["direction"]
                quads.append(quad)
            recognized = await b.ocr(config.ocr, np.array(image), quads, config, device=self.device)
            # MTU may return recognized lines in a different order. Rejoin by
            # identity, not response order. Filtered lines remain empty.
            identities = {id(quad) for quad in quads}
            by_identity = {}
            for line in recognized:
                if id(line) not in identities or id(line) in by_identity:
                    raise MtuWorkerContractError("MTU OCR 返回未知或重复文本行")
                by_identity[id(line)] = line
            ordered = [by_identity[id(quad)] for quad in quads if id(quad) in by_identity]
            text = "\n".join(str(line.text) for line in ordered if line.text)
            confidence = float(np.mean([line.prob for line in ordered])) if ordered and engine != "mocr" else None
            item = {"id": region["id"], "text": text, "confidence": confidence,
                    "confidenceSupported": confidence is not None, "engine": "mtu-" + engine,
                    "primaryEngine": "mtu-" + engine, "fallbackUsed": False}
            if colors:
                def average(channel):
                    return np.mean([getattr(line, channel) for line in ordered], axis=0).round().astype(int).tolist() if ordered else None
                item.update(fg_color=average("fg_colors"), bg_color=average("bg_colors"))
            results.append(item)
        return {"results": results}

    async def inpaint(self, image, mask, options):
        b = self.bindings()
        model = options.get("inpainter", "lama_mpe")
        if model not in {"lama_mpe", "lama_large", "default"}:
            raise MtuWorkerContractError("该 MTU inpaint 模型尚未适配")
        config = b.config.InpainterConfig(inpainter=b.config.Inpainter(model),
                                         inpainting_size=options.get("inpainting_size", 1024),
                                         force_use_torch_inpainting=True)
        output = await b.inpaint(config.inpainter, np.array(image), np.array(mask), config,
                                 inpainting_size=config.inpainting_size, device=self.device, verbose=False)
        return {"image": encode_worker_png(Image.fromarray(output))}


class MtuWorkerRuntime:
    def __init__(self, engine=None):
        self.engine = engine or PinnedMtuEngine()

    async def execute(self, payload):
        stage = payload.get("stage")
        if payload.get("contract_version") != MTU_WORKER_CONTRACT_VERSION or stage not in OPTION_KEYS:
            raise MtuWorkerContractError("Worker 契约版本或阶段无效")
        allowed = {"contract_version", "stage", "image", "options", "regions", "mask"}
        if set(payload) - allowed:
            raise MtuWorkerContractError("Worker 请求包含未定义字段")
        options = payload.get("options", {})
        if not isinstance(options, dict) or set(options) - OPTION_KEYS[stage]:
            raise MtuWorkerContractError("Worker 参数不在该阶段允许列表内")
        image = decode_worker_png(payload.get("image"))
        if stage == "detect":
            result = await self.engine.detect(image, options)
        elif stage in {"ocr", "color"}:
            regions = payload.get("regions")
            if not isinstance(regions, list):
                raise MtuWorkerContractError("Worker regions 必须为数组")
            seen = set()
            for region in regions:
                ident = region.get("id")
                if not isinstance(ident, str) or not ident or ident in seen:
                    raise MtuWorkerContractError("Worker 区域 ID 缺失或重复")
                seen.add(ident)
                coord = _coords(region.get("coords"), "Worker region")
                if coord[0] < 0 or coord[1] < 0 or coord[2] > image.width or coord[3] > image.height:
                    raise MtuWorkerContractError("Worker region 超出原图")
                for line in region.get("textlines", []):
                    polygon_points(line["polygon"], image.width, image.height)
            result = await self.engine.recognize(image, regions, options, colors=stage == "color")
        else:
            mask = decode_worker_png(payload.get("mask"), mode="L")
            if mask.size != image.size:
                raise MtuWorkerContractError("Worker mask 尺寸与原图不符")
            result = await self.engine.inpaint(image, mask, options)
        return {"contract_version": MTU_WORKER_CONTRACT_VERSION, "stage": stage,
                "mtu_revision": MTU_REVISION, **result}
