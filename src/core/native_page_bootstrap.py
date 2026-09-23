"""Server-owned registration for the native MTU whole-page engine."""

import json
import os

from src.core.modal_worker_client import ModalWorkerClient
from src.core.native_mtu_page_contract import (
    EXTRACT_OPTION_GROUPS,
    RENDER_OPTION_GROUPS,
    build_native_mtu_extract_request,
    build_native_mtu_render_request,
)
from src.core.page_engines import NativeMtuPageEngine, register_page_engine


def _translator(config, injected=None):
    if injected is not None:
        return injected
    backend = str(config.get("backend", "deepseek") or "").strip().lower()
    if backend == "deepseek":
        from src.core.stage_backends.deepseek import DeepSeekTranslationBackend

        options = {"model": config.get("model")}
        if config.get("api_key_env") is not None:
            options["api_key_env"] = config["api_key_env"]
        return DeepSeekTranslationBackend(**options)

    # Third-party adapters use the existing translation-stage plugin registry.
    from src.core.stage_backends import create_stage_backend

    def unavailable_local_translator(*_args, **_kwargs):
        raise RuntimeError("未配置本地翻译适配器")

    return create_stage_backend(
        "translate",
        backend,
        local_handler=unavailable_local_translator,
    )


def configure_native_mtu_page_engine(
    config,
    *,
    worker_client=None,
    translation_backend=None,
):
    if not isinstance(config, dict) or set(config) - {"worker", "page", "translation"}:
        raise ValueError("原生 MTU 配置只允许 worker、page、translation")
    worker = config.get("worker")
    if not isinstance(worker, dict) or set(worker) - {"app_name", "class_name", "environment_name"}:
        raise ValueError("原生 MTU Worker 配置无效")
    if not isinstance(worker.get("app_name"), str) or not worker["app_name"].strip():
        raise ValueError("请配置原生 MTU Modal app_name")
    options = config.get("page", {})
    if not isinstance(options, dict):
        raise ValueError("原生 MTU page 配置必须是对象")
    if set(options) - {"detector", "ocr", "inpainter", "render", "controller"}:
        raise ValueError("page 只允许 MTU 图像模块；翻译器请放在 translation")
    translation = config.get("translation", {})
    allowed_translation = {
        "backend",
        "model",
        "api_key_env",
        "target_language",
        "prompt_content",
    }
    if not isinstance(translation, dict) or set(translation) - allowed_translation:
        raise ValueError("translation 配置字段无效")
    target_language = translation.get("target_language")
    if not isinstance(target_language, str) or not target_language.strip():
        raise ValueError("translation.target_language 不能为空")
    if translation.get("prompt_content") is not None and not isinstance(
        translation["prompt_content"], str
    ):
        raise ValueError("translation.prompt_content 必须是字符串")
    page_options = {key: dict(value) for key, value in options.items()}
    page_options["translator"] = {"target_lang": target_language.strip()}

    # Reuse both wire validators without loading a model or opening a connection.
    from PIL import Image

    fixture = Image.new("RGB", (1, 1))
    extract_options = {
        key: value for key, value in page_options.items()
        if key in EXTRACT_OPTION_GROUPS
    }
    render_options = {
        key: value for key, value in page_options.items()
        if key in RENDER_OPTION_GROUPS
    }
    build_native_mtu_extract_request(fixture, extract_options)
    build_native_mtu_render_request(
        fixture,
        Image.new("L", (1, 1)),
        {
            "schema": "mtu-extraction/v1",
            "original_width": 1,
            "original_height": 1,
            "regions": [],
        },
        {},
        render_options,
    )
    translator = _translator(translation, translation_backend)
    client = worker_client or ModalWorkerClient(**worker)
    register_page_engine(
        "mtu_native",
        lambda: NativeMtuPageEngine(
            client,
            page_options,
            translator,
            {
                "target_language": target_language.strip(),
                "prompt_content": translation.get("prompt_content"),
            },
        ),
        replace=True,
    )


def configure_native_mtu_page_engine_from_env():
    path = os.environ.get("SABER_NATIVE_MTU_CONFIG")
    if path:
        with open(path, encoding="utf-8") as handle:
            configure_native_mtu_page_engine(json.load(handle))
