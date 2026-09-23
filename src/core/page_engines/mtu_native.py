"""Headless orchestration around MTU's native translation seam."""

from typing import Any, Mapping, Sequence

from PIL import Image

from src.core.native_mtu_page_contract import (
    DEFAULT_NATIVE_MTU_GPU_BATCH_PAGES,
    EXTRACT_OPTION_GROUPS,
    MAX_NATIVE_MTU_BATCH_PAGES,
    RENDER_OPTION_GROUPS,
    build_native_mtu_extract_batch_request,
    build_native_mtu_extract_request,
    build_native_mtu_render_batch_request,
    build_native_mtu_render_request,
    normalize_native_mtu_extract_batch_response,
    normalize_native_mtu_extract_response,
    normalize_native_mtu_render_batch_response,
    normalize_native_mtu_render_response,
)

from .base import PageEngineResult


class NativeMtuPageEngine:
    """Extract with MTU, translate through an adapter, then resume MTU."""

    name = "mtu_native"

    def __init__(
        self,
        executor,
        options: Mapping[str, Any],
        translator,
        translation_options: Mapping[str, Any],
    ):
        self._executor = executor
        self._options = {key: dict(value) for key, value in options.items()}
        self._translator = translator
        self._translation_options = dict(translation_options)

    def _operation_options(self, groups: set[str]) -> dict[str, dict[str, Any]]:
        return {
            group: dict(self._options[group])
            for group in groups
            if group in self._options
        }

    def extract_page(self, image: Image.Image) -> dict[str, Any]:
        request = build_native_mtu_extract_request(
            image,
            self._operation_options(EXTRACT_OPTION_GROUPS),
        )
        response = self._executor.execute(request)
        return normalize_native_mtu_extract_response(
            response,
            image_size=image.size,
        )

    def extract_pages(
        self,
        pages: Sequence[tuple[str, Image.Image]],
    ) -> list[dict[str, Any]]:
        request = build_native_mtu_extract_batch_request(
            pages,
            self._operation_options(EXTRACT_OPTION_GROUPS),
        )
        response = self._executor.execute(request)
        return normalize_native_mtu_extract_batch_response(
            response,
            page_sizes={page_id: image.size for page_id, image in pages},
        )

    def translate_regions(
        self,
        extraction_document: Mapping[str, Any],
    ) -> dict[str, str]:
        translated = self.translate_pages([{
            "page_id": "single-page",
            "extraction_document": extraction_document,
        }])
        return translated["single-page"]

    def translate_pages(
        self,
        extractions: Sequence[Mapping[str, Any]],
    ) -> dict[str, dict[str, str]]:
        page_ids = []
        flattened = []
        for extraction in extractions:
            page_id = extraction.get("page_id")
            if (
                not isinstance(page_id, str)
                or not page_id
                or page_id in page_ids
            ):
                raise ValueError("批量翻译页面 ID 缺失或重复")
            page_ids.append(page_id)
            document = extraction.get("extraction_document")
            if not isinstance(document, Mapping):
                raise ValueError("批量翻译缺少 MTU extraction document")
            for record in list(document.get("regions") or []):
                flattened.append((page_id, record))
        texts = [record["text"] for _, record in flattened]
        translated = self._translator.execute(
            texts,
            target_language=self._translation_options["target_language"],
            prompt_content=self._translation_options.get("prompt_content"),
        )
        if (
            not isinstance(translated, (list, tuple))
            or len(translated) != len(flattened)
            or any(not isinstance(value, str) for value in translated)
        ):
            raise ValueError("翻译适配器必须为每个 MTU 区域返回一个字符串")
        result = {page_id: {} for page_id in page_ids}
        for (page_id, record), value in zip(flattened, translated):
            result[page_id][record["id"]] = value
        return result

    def render_page(
        self,
        extraction: Mapping[str, Any],
        translations: Mapping[str, str],
    ) -> dict[str, Any]:
        request = build_native_mtu_render_request(
            extraction["working_image"],
            extraction["raw_mask"],
            extraction["extraction_document"],
            translations,
            self._operation_options(RENDER_OPTION_GROUPS),
        )
        response = self._executor.execute(request)
        return normalize_native_mtu_render_response(
            response,
            image_size=extraction["working_image"].size,
        )

    def render_pages(
        self,
        extractions: Sequence[Mapping[str, Any]],
        translations: Mapping[str, Mapping[str, str]],
    ) -> list[dict[str, Any]]:
        pages = [{
            "id": extraction["page_id"],
            "working_image": extraction["working_image"],
            "raw_mask": extraction["raw_mask"],
            "extraction_document": extraction["extraction_document"],
            "translations": translations[extraction["page_id"]],
        } for extraction in extractions]
        request = build_native_mtu_render_batch_request(
            pages,
            self._operation_options(RENDER_OPTION_GROUPS),
        )
        response = self._executor.execute(request)
        return normalize_native_mtu_render_batch_response(
            response,
            page_sizes={
                extraction["page_id"]: extraction["working_image"].size
                for extraction in extractions
            },
        )

    def _result(
        self,
        extraction: Mapping[str, Any],
        rendered: Mapping[str, Any],
        translations: Mapping[str, str],
        *,
        batch_page_count: int = 1,
    ) -> PageEngineResult:
        metadata = dict(rendered["metadata"])
        metadata.update({
            "translationBackend": getattr(
                self._translator, "name", type(self._translator).__name__
            ),
            "regionCount": len(translations),
            "translationBatchPageCount": batch_page_count,
        })
        return PageEngineResult(
            engine=self.name,
            clean_image=rendered["clean_image"],
            final_image=rendered["final_image"],
            repair_mask=rendered["repair_mask"],
            native_document=rendered["native_document"],
            warnings=list(extraction["warnings"]) + list(rendered["warnings"]),
            metadata=metadata,
        )

    def execute(self, image: Image.Image, **overrides: Any) -> PageEngineResult:
        if overrides:
            raise ValueError("原生 MTU 整页参数只能由服务器配置，不能由请求覆盖")
        extraction = self.extract_page(image.convert("RGB"))
        translations = self.translate_regions(extraction["extraction_document"])
        rendered = self.render_page(extraction, translations)
        return self._result(extraction, rendered, translations)

    def execute_batch(
        self,
        images: Sequence[Image.Image],
        *,
        gpu_batch_size: int = DEFAULT_NATIVE_MTU_GPU_BATCH_PAGES,
    ) -> list[PageEngineResult]:
        if (
            isinstance(gpu_batch_size, bool)
            or not isinstance(gpu_batch_size, int)
            or not 1 <= gpu_batch_size <= MAX_NATIVE_MTU_BATCH_PAGES
        ):
            raise ValueError(
                f"gpu_batch_size 必须在 1 到 {MAX_NATIVE_MTU_BATCH_PAGES} 之间"
            )
        sources = [image.convert("RGB") for image in images]
        if not sources:
            return []
        identified = [
            (f"page-{index:06d}", image)
            for index, image in enumerate(sources)
        ]
        extractions = []
        for start in range(0, len(identified), gpu_batch_size):
            extractions.extend(self.extract_pages(
                identified[start:start + gpu_batch_size]
            ))

        translations = self.translate_pages(extractions)
        rendered_pages = []
        for start in range(0, len(extractions), gpu_batch_size):
            rendered_pages.extend(self.render_pages(
                extractions[start:start + gpu_batch_size],
                translations,
            ))
        rendered_by_id = {
            rendered["page_id"]: rendered for rendered in rendered_pages
        }
        return [
            self._result(
                extraction,
                rendered_by_id[extraction["page_id"]],
                translations[extraction["page_id"]],
                batch_page_count=len(sources),
            )
            for extraction in extractions
        ]
