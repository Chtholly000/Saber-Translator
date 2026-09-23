"""Versioned split boundary around MTU's native page controller.

The GPU worker owns image stages. Translation stays on the control plane and
is joined back to MTU regions by stable IDs. The wire format deliberately
keeps each complete TextBlock.to_dict() payload instead of projecting it into
Saber's smaller editor model.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from PIL import Image

from src.core.mtu_worker_contract import (
    MtuWorkerContractError,
    decode_worker_png,
    encode_worker_png,
)


NATIVE_MTU_PAGE_CONTRACT_VERSION = "saber-native-mtu-page/v3"
PINNED_MTU_REVISION = "f0307a063214f915f2b1d6e5cd3233f3bf78339f"
DEFAULT_NATIVE_MTU_GPU_BATCH_PAGES = 4
MAX_NATIVE_MTU_BATCH_PAGES = 8

# These are configuration seams already owned by the pinned MTU Config. The
# split wrapper only decides where execution pauses for an external translator.
NATIVE_MTU_OPTION_KEYS = {
    "detector": {
        "detector",
        "detection_size",
        "text_threshold",
        "box_threshold",
        "unclip_ratio",
        "min_box_area_ratio",
        "det_rearrange_min_effective_short_side",
    },
    "ocr": {
        "ocr",
        "prob",
        "ignore_bubble",
        "use_model_bubble_filter",
        "model_bubble_overlap_threshold",
        "use_model_bubble_repair_intersection",
        "limit_mask_dilation_to_bubble_mask",
        "merge_gamma",
        "merge_sigma",
    },
    # Provider, model and credentials belong to the independently replaceable
    # control-plane translator. MTU only needs the language semantics.
    "translator": {"target_lang"},
    "inpainter": {
        "inpainter",
        "inpainting_size",
        "inpainting_precision",
        "force_use_torch_inpainting",
        "solid_fill_pure_bubbles",
        "per_block_inpainting",
    },
    "render": {
        "renderer",
        "layout_mode",
        "alignment",
        "direction",
        "font_family",
        "font_size",
        "font_size_offset",
        "font_size_minimum",
        "max_font_size",
        "font_scale_ratio",
        "center_text_in_bubble",
        "optimize_line_breaks",
        "strict_smart_scaling",
        "force_strict_layout",
        "disable_font_border",
        "disable_auto_wrap",
        "stroke_width",
        "line_spacing",
        "letter_spacing",
    },
    "controller": {"mask_dilation_offset", "kernel_size"},
}

EXTRACT_OPTION_GROUPS = {"detector", "ocr", "translator", "render", "controller"}
RENDER_OPTION_GROUPS = {"ocr", "translator", "inpainter", "render", "controller"}


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MtuWorkerContractError(f"{field} 必须是对象")
    return value


def _safe_options(
    options: Mapping[str, Any],
    *,
    groups: set[str],
) -> Dict[str, Dict[str, Any]]:
    value = _mapping(options, "原生 MTU options")
    unknown_groups = set(value) - groups
    if unknown_groups:
        raise MtuWorkerContractError(
            "当前操作包含无效模块: " + ", ".join(sorted(unknown_groups))
        )
    normalized: Dict[str, Dict[str, Any]] = {}
    for group, raw_values in value.items():
        values = _mapping(raw_values, group)
        unknown = set(values) - NATIVE_MTU_OPTION_KEYS[group]
        if unknown:
            raise MtuWorkerContractError(
                f"{group} 包含未定义参数: {', '.join(sorted(unknown))}"
            )
        for key in values:
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("key", "token", "secret")):
                raise MtuWorkerContractError("原生 MTU Worker 请求不得携带凭据")
        normalized[group] = dict(values)
    return normalized


def validate_native_mtu_extraction_document(value: Any) -> Dict[str, Any]:
    document = dict(_mapping(value, "extraction_document"))
    if document.get("schema") != "mtu-extraction/v1":
        raise MtuWorkerContractError("MTU 提取文档版本无效")
    regions = document.get("regions")
    if not isinstance(regions, list):
        raise MtuWorkerContractError("extraction_document.regions 必须是数组")
    seen = set()
    for record in regions:
        if not isinstance(record, Mapping):
            raise MtuWorkerContractError("MTU 区域记录必须是对象")
        ident = record.get("id")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise MtuWorkerContractError("MTU 区域 ID 缺失或重复")
        seen.add(ident)
        if not isinstance(record.get("text"), str):
            raise MtuWorkerContractError("MTU 区域原文必须是字符串")
        native = record.get("native")
        if not isinstance(native, Mapping) or not isinstance(native.get("lines"), list):
            raise MtuWorkerContractError("MTU 区域缺少完整 native TextBlock 数据")
    return document


def build_native_mtu_extract_request(
    image: Image.Image,
    options: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "contract_version": NATIVE_MTU_PAGE_CONTRACT_VERSION,
        "operation": "extract_page",
        "image": encode_worker_png(image.convert("RGB")),
        "options": _safe_options(options, groups=EXTRACT_OPTION_GROUPS),
    }


def _batch_page_ids(pages: Sequence[Mapping[str, Any]]) -> list[str]:
    if (
        not isinstance(pages, Sequence)
        or isinstance(pages, (str, bytes))
        or not pages
        or len(pages) > MAX_NATIVE_MTU_BATCH_PAGES
    ):
        raise MtuWorkerContractError(
            f"原生 MTU 批次必须包含 1 到 {MAX_NATIVE_MTU_BATCH_PAGES} 页"
        )
    page_ids = []
    for page in pages:
        if not isinstance(page, Mapping):
            raise MtuWorkerContractError("原生 MTU 批次页面必须是对象")
        page_id = page.get("id")
        if not isinstance(page_id, str) or not page_id or page_id in page_ids:
            raise MtuWorkerContractError("原生 MTU 批次页面 ID 缺失或重复")
        page_ids.append(page_id)
    return page_ids


def build_native_mtu_extract_batch_request(
    pages: Sequence[tuple[str, Image.Image]],
    options: Mapping[str, Any],
) -> Dict[str, Any]:
    records = [
        {"id": page_id, "image": encode_worker_png(image.convert("RGB"))}
        for page_id, image in pages
    ]
    _batch_page_ids(records)
    return {
        "contract_version": NATIVE_MTU_PAGE_CONTRACT_VERSION,
        "operation": "extract_pages",
        "pages": records,
        "options": _safe_options(options, groups=EXTRACT_OPTION_GROUPS),
    }


def normalize_native_mtu_extract_response(
    payload: Mapping[str, Any],
    *,
    image_size: tuple[int, int],
) -> Dict[str, Any]:
    value = _mapping(payload, "原生 MTU extraction response")
    if value.get("contract_version") != NATIVE_MTU_PAGE_CONTRACT_VERSION:
        raise MtuWorkerContractError("原生 MTU 契约版本不兼容")
    if value.get("operation") != "extract_page":
        raise MtuWorkerContractError("原生 MTU Worker operation 不匹配")
    if value.get("mtu_revision") != PINNED_MTU_REVISION:
        raise MtuWorkerContractError("原生 MTU Worker revision 不匹配")
    working = decode_worker_png(value.get("working_image"))
    raw_mask = decode_worker_png(value.get("raw_mask"), mode="L")
    if working.size != image_size or raw_mask.size != image_size:
        raise MtuWorkerContractError("MTU 提取图片尺寸与输入不一致")
    document = validate_native_mtu_extraction_document(
        value.get("extraction_document")
    )
    if (document.get("original_width"), document.get("original_height")) != image_size:
        raise MtuWorkerContractError("MTU 提取文档尺寸与输入不一致")
    return {
        "working_image": working,
        "raw_mask": raw_mask,
        "extraction_document": document,
        "warnings": _warnings(value.get("warnings", [])),
        "metadata": {
            "mtuRevision": value["mtu_revision"],
            "engineMode": "native-split",
        },
    }


def normalize_native_mtu_extract_batch_response(
    payload: Mapping[str, Any],
    *,
    page_sizes: Mapping[str, tuple[int, int]],
) -> list[Dict[str, Any]]:
    value = _mapping(payload, "原生 MTU batch extraction response")
    if value.get("contract_version") != NATIVE_MTU_PAGE_CONTRACT_VERSION:
        raise MtuWorkerContractError("原生 MTU 契约版本不兼容")
    if value.get("operation") != "extract_pages":
        raise MtuWorkerContractError("原生 MTU Worker batch operation 不匹配")
    if value.get("mtu_revision") != PINNED_MTU_REVISION:
        raise MtuWorkerContractError("原生 MTU Worker revision 不匹配")
    pages = value.get("pages")
    if not isinstance(pages, list):
        raise MtuWorkerContractError("原生 MTU 批次响应缺少 pages")
    response_ids = _batch_page_ids(pages)
    if set(response_ids) != set(page_sizes) or len(response_ids) != len(page_sizes):
        raise MtuWorkerContractError("原生 MTU 批次响应页面 ID 不匹配")
    by_id = {}
    for page in pages:
        page_id = page["id"]
        by_id[page_id] = normalize_native_mtu_extract_response(
            {
                "contract_version": value["contract_version"],
                "operation": "extract_page",
                "mtu_revision": value["mtu_revision"],
                **{key: item for key, item in page.items() if key != "id"},
            },
            image_size=page_sizes[page_id],
        )
    return [{"page_id": page_id, **by_id[page_id]} for page_id in page_sizes]


def _translation_map(
    document: Mapping[str, Any],
    translations: Mapping[str, str] | Sequence[Mapping[str, str]],
) -> Dict[str, str]:
    expected = [record["id"] for record in document["regions"]]
    if isinstance(translations, Mapping):
        result = dict(translations)
    elif isinstance(translations, Sequence) and not isinstance(translations, (str, bytes)):
        result = {}
        for record in translations:
            if not isinstance(record, Mapping):
                raise MtuWorkerContractError("译文记录必须是对象")
            ident, translated = record.get("id"), record.get("text")
            if (
                not isinstance(ident, str)
                or ident in result
                or not isinstance(translated, str)
            ):
                raise MtuWorkerContractError("译文 ID 缺失、重复或内容无效")
            result[ident] = translated
    else:
        raise MtuWorkerContractError("translations 必须按区域 ID 提供")
    if set(result) != set(expected) or any(
        not isinstance(item, str) for item in result.values()
    ):
        raise MtuWorkerContractError("译文 ID 必须与提取区域一一对应")
    return {ident: result[ident] for ident in expected}


def build_native_mtu_render_request(
    working_image: Image.Image,
    raw_mask: Image.Image,
    extraction_document: Mapping[str, Any],
    translations: Mapping[str, str] | Sequence[Mapping[str, str]],
    options: Mapping[str, Any],
) -> Dict[str, Any]:
    document = validate_native_mtu_extraction_document(extraction_document)
    if raw_mask.size != working_image.size:
        raise MtuWorkerContractError("raw_mask 与 working_image 尺寸不一致")
    if (
        document.get("original_width"),
        document.get("original_height"),
    ) != working_image.size:
        raise MtuWorkerContractError("提取文档与 working_image 尺寸不一致")
    return {
        "contract_version": NATIVE_MTU_PAGE_CONTRACT_VERSION,
        "operation": "render_page",
        "image": encode_worker_png(working_image.convert("RGB")),
        "raw_mask": encode_worker_png(raw_mask.convert("L")),
        "extraction_document": document,
        "translations": _translation_map(document, translations),
        "options": _safe_options(options, groups=RENDER_OPTION_GROUPS),
    }


def build_native_mtu_render_batch_request(
    pages: Sequence[Mapping[str, Any]],
    options: Mapping[str, Any],
) -> Dict[str, Any]:
    records = []
    for page in pages:
        value = _mapping(page, "原生 MTU render batch page")
        page_id = value.get("id")
        single = build_native_mtu_render_request(
            value.get("working_image"),
            value.get("raw_mask"),
            value.get("extraction_document"),
            value.get("translations"),
            options,
        )
        records.append({
            "id": page_id,
            "image": single["image"],
            "raw_mask": single["raw_mask"],
            "extraction_document": single["extraction_document"],
            "translations": single["translations"],
        })
    _batch_page_ids(records)
    return {
        "contract_version": NATIVE_MTU_PAGE_CONTRACT_VERSION,
        "operation": "render_pages",
        "pages": records,
        "options": _safe_options(options, groups=RENDER_OPTION_GROUPS),
    }


def normalize_native_mtu_render_response(
    payload: Mapping[str, Any],
    *,
    image_size: tuple[int, int],
) -> Dict[str, Any]:
    value = _mapping(payload, "原生 MTU render response")
    if value.get("contract_version") != NATIVE_MTU_PAGE_CONTRACT_VERSION:
        raise MtuWorkerContractError("原生 MTU 契约版本不兼容")
    if value.get("operation") != "render_page":
        raise MtuWorkerContractError("原生 MTU Worker operation 不匹配")
    if value.get("mtu_revision") != PINNED_MTU_REVISION:
        raise MtuWorkerContractError("原生 MTU Worker revision 不匹配")
    clean = decode_worker_png(value.get("clean_image"))
    final = decode_worker_png(value.get("final_image"))
    mask = decode_worker_png(value.get("repair_mask"), mode="L")
    if clean.size != image_size or final.size != image_size or mask.size != image_size:
        raise MtuWorkerContractError("原生 MTU 返回图片尺寸与输入不一致")
    native_document = dict(_mapping(value.get("native_document"), "native_document"))
    if native_document.get("schema") != "mtu-rendered/v1":
        raise MtuWorkerContractError("MTU 成图文档版本无效")
    validate_native_mtu_extraction_document({
        "schema": "mtu-extraction/v1",
        "original_width": image_size[0],
        "original_height": image_size[1],
        "regions": native_document.get("regions"),
    })
    return {
        "clean_image": clean,
        "final_image": final,
        "repair_mask": mask,
        "native_document": native_document,
        "warnings": _warnings(value.get("warnings", [])),
        "metadata": {
            "mtuRevision": value["mtu_revision"],
            "engineMode": "native-split",
        },
    }


def normalize_native_mtu_render_batch_response(
    payload: Mapping[str, Any],
    *,
    page_sizes: Mapping[str, tuple[int, int]],
) -> list[Dict[str, Any]]:
    value = _mapping(payload, "原生 MTU batch render response")
    if value.get("contract_version") != NATIVE_MTU_PAGE_CONTRACT_VERSION:
        raise MtuWorkerContractError("原生 MTU 契约版本不兼容")
    if value.get("operation") != "render_pages":
        raise MtuWorkerContractError("原生 MTU Worker batch operation 不匹配")
    if value.get("mtu_revision") != PINNED_MTU_REVISION:
        raise MtuWorkerContractError("原生 MTU Worker revision 不匹配")
    pages = value.get("pages")
    if not isinstance(pages, list):
        raise MtuWorkerContractError("原生 MTU 批次响应缺少 pages")
    response_ids = _batch_page_ids(pages)
    if set(response_ids) != set(page_sizes) or len(response_ids) != len(page_sizes):
        raise MtuWorkerContractError("原生 MTU 批次响应页面 ID 不匹配")
    by_id = {}
    for page in pages:
        page_id = page["id"]
        by_id[page_id] = normalize_native_mtu_render_response(
            {
                "contract_version": value["contract_version"],
                "operation": "render_page",
                "mtu_revision": value["mtu_revision"],
                **{key: item for key, item in page.items() if key != "id"},
            },
            image_size=page_sizes[page_id],
        )
    return [{"page_id": page_id, **by_id[page_id]} for page_id in page_sizes]


def _warnings(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise MtuWorkerContractError("warnings 必须是对象数组")
    return [dict(item) for item in value]
