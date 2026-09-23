"""Thin split adapter around the pinned MTU controller.

Extraction calls MTU's own pre-translation controller path. Completion
rehydrates native TextBlocks, injects translations by stable region ID and
calls MTU's own post-translation controller path. No detection, OCR, mask,
inpainting, layout or rendering algorithm is reimplemented here.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import math
from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np
from PIL import Image

from src.core.mtu_worker_contract import (
    MtuWorkerContractError,
    decode_worker_png,
    encode_worker_png,
)
from src.core.blank_bubble_contract import (
    BLANK_BUBBLE_CONTRACT_VERSION,
    validate_bubble_options,
)
from src.core.native_mtu_page_contract import (
    EXTRACT_OPTION_GROUPS,
    MAX_NATIVE_MTU_BATCH_PAGES,
    NATIVE_MTU_OPTION_KEYS,
    NATIVE_MTU_PAGE_CONTRACT_VERSION,
    PINNED_MTU_REVISION,
    RENDER_OPTION_GROUPS,
    validate_native_mtu_extraction_document,
)


def _image(value: Any, *, mode: str) -> Image.Image:
    if isinstance(value, Image.Image):
        return value.convert(mode)
    return Image.fromarray(np.asarray(value)).convert(mode)


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _default_bindings():
    # Deliberately lazy: importing this worker must not import torch or load MTU.
    from manga_translator.config import Config
    from manga_translator.manga_translator import MangaTranslator
    from manga_translator.utils.generic import Context
    from manga_translator.utils.textblock import TextBlock

    return SimpleNamespace(
        Config=Config,
        MangaTranslator=MangaTranslator,
        Context=Context,
        TextBlock=TextBlock,
    )


def _capturing_controller_class(base_class):
    class ArtifactCapturingController(base_class):
        async def _run_text_rendering(self, config, ctx, *args, **kwargs):
            clean = getattr(ctx, "img_inpainted", None)
            mask = getattr(ctx, "mask", None)
            if clean is not None:
                self._saber_native_clean = np.array(clean, dtype=np.uint8, copy=True)
            if mask is not None:
                self._saber_native_mask = np.array(mask, dtype=np.uint8, copy=True)
            return await super()._run_text_rendering(config, ctx, *args, **kwargs)

    return ArtifactCapturingController


async def _stop_background_jobs(controller) -> None:
    task = getattr(controller, "_detector_cleanup_task", None)
    if task is not None and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


class NativeMtuControllerAdapter:
    """Pause and resume the original MTU controller at its translation seam."""

    def __init__(self, *, bindings=None):
        self._bindings = bindings

    def bindings(self):
        if self._bindings is None:
            self._bindings = _default_bindings()
        return self._bindings

    def _config(self, options: Mapping[str, Any]):
        payload = {
            group: dict(options[group])
            for group in ("detector", "ocr", "translator", "inpainter", "render")
            if group in options
        }
        controller_options = dict(options.get("controller", {}))
        if "mask_dilation_offset" in controller_options:
            payload["mask_dilation_offset"] = controller_options[
                "mask_dilation_offset"
            ]
        return self.bindings().Config(**payload), controller_options

    def _controller(self, controller_options: Mapping[str, Any]):
        controller_class = _capturing_controller_class(
            self.bindings().MangaTranslator
        )
        return controller_class({
            "use_gpu": True,
            # Non-zero avoids eagerly loading translator/inpainter during the
            # extraction-only call; each requested MTU stage still lazy-loads.
            "models_ttl": 60,
            "ignore_errors": False,
            "kernel_size": controller_options.get("kernel_size", 3),
        })

    async def extract_page(self, image: Image.Image, options: Mapping[str, Any]):
        config, controller_options = self._config(options)
        controller = self._controller(controller_options)
        original = image.convert("RGB")
        try:
            ctx = await controller._translate_until_translation(original, config)
            working_value = getattr(ctx, "img_rgb", None)
            if working_value is None:
                working_value = original
            working = _image(working_value, mode="RGB")
            if working.size != original.size:
                raise RuntimeError(
                    "原生分段协议暂不允许提取阶段改变图片尺寸"
                )
            mask_raw_value = getattr(ctx, "mask_raw", None)
            if mask_raw_value is None:
                mask_raw_value = np.zeros(
                    (working.height, working.width), dtype=np.uint8
                )
            regions = []
            for index, region in enumerate(
                list(getattr(ctx, "text_regions", None) or [])
            ):
                if not callable(getattr(region, "to_dict", None)):
                    raise RuntimeError("MTU 原生区域缺少 to_dict 序列化接口")
                regions.append({
                    "id": f"region-{index:04d}",
                    "text": str(getattr(region, "text", "") or ""),
                    "native": _json_safe(region.to_dict()),
                })
            warnings = []
            if not regions:
                warnings.append({
                    "code": "no_text_regions",
                    "message": "MTU 未检测到文字区域",
                })
            return {
                "working_image": encode_worker_png(working),
                "raw_mask": encode_worker_png(_image(mask_raw_value, mode="L")),
                "extraction_document": {
                    "schema": "mtu-extraction/v1",
                    "original_width": working.width,
                    "original_height": working.height,
                    "regions": regions,
                    "module_selection": _json_safe(dict(options)),
                },
                "warnings": warnings,
            }
        finally:
            await _stop_background_jobs(controller)

    def _rehydrate_region(
        self,
        native: Mapping[str, Any],
        *,
        translation: str,
        target_lang: str | None,
    ):
        data = dict(native)
        center = data.pop("center", None)
        if "fg_colors" in data:
            data["fg_color"] = tuple(data.pop("fg_colors"))
        if "bg_colors" in data:
            data["bg_color"] = tuple(data.pop("bg_colors"))
        if "stroke_width" in data:
            data["default_stroke_width"] = data.pop("stroke_width")
        lines = np.asarray(data.get("lines"), dtype=np.float64)
        if lines.ndim == 2 and lines.shape == (4, 2):
            lines = lines.reshape(1, 4, 2)
        if lines.ndim != 3 or lines.shape[1:] != (4, 2):
            raise MtuWorkerContractError("MTU native TextBlock lines 形状无效")
        try:
            angle = float(data.get("angle", 0) or 0)
        except (TypeError, ValueError) as error:
            raise MtuWorkerContractError("MTU native TextBlock angle 无效") from error
        if not np.isfinite(angle) or not np.all(np.isfinite(lines)):
            raise MtuWorkerContractError("MTU native TextBlock 几何坐标无效")
        if angle:
            try:
                pivot = np.asarray(center, dtype=np.float64)
            except (TypeError, ValueError) as error:
                raise MtuWorkerContractError(
                    "倾斜 MTU 区域缺少有效 center"
                ) from error
            if pivot.shape != (2,) or not np.all(np.isfinite(pivot)):
                raise MtuWorkerContractError("倾斜 MTU 区域缺少有效 center")
            # Pinned MTU TextBlock.to_dict() counter-rotates its lines around
            # center for project serialization. Restore the live geometry
            # before resuming MTU's mask, inpainting and rendering stages.
            radians = math.radians(angle)
            cosine, sine = math.cos(radians), math.sin(radians)
            x = lines[..., 0] - pivot[0]
            y = lines[..., 1] - pivot[1]
            lines = np.stack((
                x * cosine - y * sine + pivot[0],
                x * sine + y * cosine + pivot[1],
            ), axis=-1)
        data["lines"] = lines
        texts = data.get("texts")
        if not isinstance(texts, list) or not texts:
            data["texts"] = [str(data.get("text", "") or "")]
        data["translation"] = translation
        data["translation_raw"] = translation
        # An old rich payload must not override the newly selected translator.
        data["translation_rich"] = None
        if target_lang:
            data["target_lang"] = target_lang
        return self.bindings().TextBlock(**data)

    async def render_page(
        self,
        image: Image.Image,
        raw_mask: Image.Image,
        extraction_document: Mapping[str, Any],
        translations: Mapping[str, str],
        options: Mapping[str, Any],
    ):
        config, controller_options = self._config(options)
        controller = self._controller(controller_options)
        target_lang = str(
            options.get("translator", {}).get("target_lang", "") or ""
        )
        records = list(extraction_document.get("regions") or [])
        regions = [
            self._rehydrate_region(
                record["native"],
                translation=translations[record["id"]],
                target_lang=target_lang or None,
            )
            for record in records
        ]
        working = image.convert("RGB")
        working_array = np.array(working, dtype=np.uint8, copy=True)
        mask_array = np.array(raw_mask.convert("L"), dtype=np.uint8, copy=True)
        ctx = self.bindings().Context(
            input=working,
            upscaled=working,
            img_rgb=working_array,
            img_alpha=None,
            mask_raw=mask_array,
            mask=None,
            text_regions=regions,
            result=None,
        )
        try:
            ctx = await controller._complete_translation_pipeline(ctx, config)
            if getattr(ctx, "result", None) is None:
                raise RuntimeError("MTU 原生完成阶段没有返回最终图片")
            clean = getattr(controller, "_saber_native_clean", working_array)
            mask = getattr(
                controller,
                "_saber_native_mask",
                np.zeros(working_array.shape[:2], dtype=np.uint8),
            )
            rendered_regions = []
            for record, region in zip(records, regions):
                rendered_regions.append({
                    "id": record["id"],
                    "text": str(getattr(region, "text", "") or ""),
                    "native": _json_safe(region.to_dict()),
                })
            return {
                "clean_image": encode_worker_png(_image(clean, mode="RGB")),
                "final_image": encode_worker_png(_image(ctx.result, mode="RGB")),
                "repair_mask": encode_worker_png(_image(mask, mode="L")),
                "native_document": {
                    "schema": "mtu-rendered/v1",
                    "original_width": working.width,
                    "original_height": working.height,
                    "regions": rendered_regions,
                    "module_selection": _json_safe(dict(options)),
                },
                "warnings": [],
            }
        finally:
            await _stop_background_jobs(controller)


def _validate_options(options: Any, groups: set[str]) -> Mapping[str, Any]:
    if not isinstance(options, Mapping) or set(options) - groups:
        raise MtuWorkerContractError("Worker 模块配置无效")
    for group, values in options.items():
        if (
            not isinstance(values, Mapping)
            or set(values) - NATIVE_MTU_OPTION_KEYS[group]
        ):
            raise MtuWorkerContractError(f"Worker {group} 参数无效")
        if any(
            marker in str(key).lower()
            for key in values
            for marker in ("key", "token", "secret")
        ):
            raise MtuWorkerContractError("Worker 请求不得携带凭据")
    return options


class MtuNativeWorkerRuntime:
    def __init__(self, engine=None, bubble_detector=None):
        self.engine = engine or NativeMtuControllerAdapter()
        self.bubble_detector = bubble_detector

    @staticmethod
    def _batch_pages(value: Any) -> list[Mapping[str, Any]]:
        if (
            not isinstance(value, list)
            or not value
            or len(value) > MAX_NATIVE_MTU_BATCH_PAGES
        ):
            raise MtuWorkerContractError(
                f"Worker 批次必须包含 1 到 {MAX_NATIVE_MTU_BATCH_PAGES} 页"
            )
        seen = set()
        for page in value:
            if not isinstance(page, Mapping):
                raise MtuWorkerContractError("Worker 批次页面必须是对象")
            page_id = page.get("id")
            if not isinstance(page_id, str) or not page_id or page_id in seen:
                raise MtuWorkerContractError("Worker 批次页面 ID 缺失或重复")
            seen.add(page_id)
        return value

    @staticmethod
    def _render_inputs(page: Mapping[str, Any]):
        expected = {
            "id",
            "image",
            "raw_mask",
            "extraction_document",
            "translations",
        }
        if set(page) != expected:
            raise MtuWorkerContractError("成图批次页面字段不完整或包含未定义字段")
        document = validate_native_mtu_extraction_document(
            page.get("extraction_document")
        )
        translations = page.get("translations")
        if not isinstance(translations, Mapping):
            raise MtuWorkerContractError("成图请求缺少提取文档或译文")
        records = document.get("regions")
        if not isinstance(records, list):
            raise MtuWorkerContractError("提取文档 regions 无效")
        expected_ids = {
            record.get("id")
            for record in records
            if isinstance(record, Mapping)
        }
        if (
            len(expected_ids) != len(records)
            or set(translations) != expected_ids
            or any(not isinstance(value, str) for value in translations.values())
        ):
            raise MtuWorkerContractError("译文 ID 必须与提取区域一一对应")
        image = decode_worker_png(page.get("image"))
        raw_mask = decode_worker_png(page.get("raw_mask"), mode="L")
        if raw_mask.size != image.size:
            raise MtuWorkerContractError("成图图片与 raw_mask 尺寸不一致")
        if (
            document.get("original_width"),
            document.get("original_height"),
        ) != image.size:
            raise MtuWorkerContractError("成图图片与提取文档尺寸不一致")
        return image, raw_mask, document, translations

    async def execute(self, payload):
        if not isinstance(payload, Mapping):
            raise MtuWorkerContractError("Worker 请求必须是对象")
        if payload.get("contract_version") == BLANK_BUBBLE_CONTRACT_VERSION:
            if set(payload) != {"contract_version", "operation", "image", "options"} or payload.get("operation") != "detect_bubbles":
                raise MtuWorkerContractError("气泡检测请求字段无效")
            options = validate_bubble_options(payload.get("options"))
            image = decode_worker_png(payload.get("image"))
            if self.bubble_detector is None:
                from workers.mtu_native.bubble_slots import MangaLensBubbleSlotDetector

                self.bubble_detector = MangaLensBubbleSlotDetector()
            slots = self.bubble_detector.detect(image, options)
            return {
                "contract_version": BLANK_BUBBLE_CONTRACT_VERSION,
                "operation": "detect_bubbles",
                "mtu_revision": PINNED_MTU_REVISION,
                "image_width": image.width,
                "image_height": image.height,
                "slots": slots,
            }
        if payload.get("contract_version") != NATIVE_MTU_PAGE_CONTRACT_VERSION:
            raise MtuWorkerContractError("Worker 契约版本无效")
        operation = payload.get("operation")
        if operation == "extract_page":
            expected = {"contract_version", "operation", "image", "options"}
            if set(payload) != expected:
                raise MtuWorkerContractError("提取请求字段不完整或包含未定义字段")
            options = _validate_options(payload.get("options"), EXTRACT_OPTION_GROUPS)
            result = await self.engine.extract_page(
                decode_worker_png(payload.get("image")),
                options,
            )
        elif operation == "extract_pages":
            expected = {"contract_version", "operation", "pages", "options"}
            if set(payload) != expected:
                raise MtuWorkerContractError("批量提取请求字段不完整或包含未定义字段")
            options = _validate_options(payload.get("options"), EXTRACT_OPTION_GROUPS)
            pages = self._batch_pages(payload.get("pages"))
            results = []
            for page in pages:
                if set(page) != {"id", "image"}:
                    raise MtuWorkerContractError("批量提取页面字段无效")
                page_result = await self.engine.extract_page(
                    decode_worker_png(page.get("image")),
                    options,
                )
                results.append({"id": page["id"], **page_result})
            result = {"pages": results}
        elif operation == "render_page":
            expected = {
                "contract_version",
                "operation",
                "image",
                "raw_mask",
                "extraction_document",
                "translations",
                "options",
            }
            if set(payload) != expected:
                raise MtuWorkerContractError("成图请求字段不完整或包含未定义字段")
            options = _validate_options(payload.get("options"), RENDER_OPTION_GROUPS)
            image, raw_mask, document, translations = self._render_inputs({
                "id": "single-page",
                "image": payload.get("image"),
                "raw_mask": payload.get("raw_mask"),
                "extraction_document": payload.get("extraction_document"),
                "translations": payload.get("translations"),
            })
            result = await self.engine.render_page(
                image,
                raw_mask,
                document,
                translations,
                options,
            )
        elif operation == "render_pages":
            expected = {"contract_version", "operation", "pages", "options"}
            if set(payload) != expected:
                raise MtuWorkerContractError("批量成图请求字段不完整或包含未定义字段")
            options = _validate_options(payload.get("options"), RENDER_OPTION_GROUPS)
            pages = self._batch_pages(payload.get("pages"))
            results = []
            for page in pages:
                image, raw_mask, document, translations = self._render_inputs(page)
                page_result = await self.engine.render_page(
                    image,
                    raw_mask,
                    document,
                    translations,
                    options,
                )
                results.append({"id": page["id"], **page_result})
            result = {"pages": results}
        else:
            raise MtuWorkerContractError("Worker operation 无效")
        return {
            "contract_version": NATIVE_MTU_PAGE_CONTRACT_VERSION,
            "operation": operation,
            "mtu_revision": PINNED_MTU_REVISION,
            **result,
        }
