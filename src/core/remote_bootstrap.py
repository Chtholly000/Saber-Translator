"""Explicit non-secret composition, separate from model loading and credentials."""

import json
import os

from src.core.extraction_backends import ModalMtuExtractionBackend, register_extraction_backend
from src.core.pipeline_profiles import register_pipeline_profile
from src.core.stage_backends import register_stage_backend
from src.core.stage_backends.mtu_inpaint import ModalMtuInpaintBackend
from src.core.stage_backends.mtu_color import ModalMtuColorBackend
from src.core.stage_backends.deepseek import DeepSeekTranslationBackend
from src.core.modal_worker_client import ModalWorkerClient
from src.core.mtu_worker_contract import MTU_MODEL_OPTION_KEYS


def configure_remote_backends(config, *, worker_client=None, translation_transport=None):
    """Register only; this function performs no inference, network call or key read."""
    if not isinstance(config, dict) or set(config) - {"worker", "models", "translation"}:
        raise ValueError("远程配置只允许 worker、models、translation")
    worker = config.get("worker", {})
    translation = config.get("translation", {})
    models = config.get("models", {})
    if not isinstance(worker, dict) or set(worker) - {"app_name", "class_name", "environment_name"}:
        raise ValueError("Worker 配置无效")
    if not isinstance(worker.get("app_name"), str) or not worker["app_name"].strip():
        raise ValueError("请配置已部署的 Modal app_name")
    if not isinstance(translation, dict) or set(translation) - {"model", "api_key_env"}:
        raise ValueError("翻译配置只允许 model、api_key_env；不要写入密钥")
    if not isinstance(models, dict) or set(models) - {"detect", "ocr", "inpaint"}:
        raise ValueError("MTU 模型配置无效")
    for stage, options in models.items():
        if not isinstance(options, dict) or set(options) - MTU_MODEL_OPTION_KEYS[stage]:
            raise ValueError(f"MTU {stage} 参数不在允许列表内")
    translator = DeepSeekTranslationBackend(**translation, transport=translation_transport)
    client = worker_client or ModalWorkerClient(**worker)
    register_extraction_backend("modal_mtu", lambda _: ModalMtuExtractionBackend(client, models), replace=True)
    register_stage_backend("inpaint", "modal_mtu", lambda _: ModalMtuInpaintBackend(client, models.get("inpaint")), replace=True)
    register_stage_backend("color", "modal_mtu", lambda _: ModalMtuColorBackend(client), replace=True)
    register_stage_backend("translate", "deepseek", lambda _: translator, replace=True)
    register_pipeline_profile("modal_mtu_deepseek", {
        "detect": "modal_mtu", "ocr": "modal_mtu", "color": "modal_mtu",
        "translate": "deepseek", "inpaint": "modal_mtu", "render": "local",
    }, replace=True)


def configure_remote_backends_from_env():
    path = os.environ.get("SABER_REMOTE_CONFIG")
    if path:
        with open(path, encoding="utf-8") as handle:
            configure_remote_backends(json.load(handle))
