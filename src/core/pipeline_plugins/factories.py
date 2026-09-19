"""Optional builtin factories. No model loading or network on import."""


def _client(worker):
    from src.core.modal_worker_client import ModalWorkerClient
    if not isinstance(worker, dict) or set(worker) - {"app_name", "class_name", "environment_name"}:
        raise ValueError("Worker 配置无效")
    if not isinstance(worker.get("app_name"), str) or not worker["app_name"].strip():
        raise ValueError("请设置 Modal app_name")
    return ModalWorkerClient(**worker)


def mtu_detect(*, worker, model=None):
    from src.core.extraction_backends.mtu_modal import ModalMtuDetectorBackend
    return ModalMtuDetectorBackend(_client(worker), {"detect": model or {}})


def mtu_ocr(*, worker, model=None):
    from src.core.extraction_backends.mtu_modal import ModalMtuOcrBackend
    return ModalMtuOcrBackend(_client(worker), {"ocr": model or {}})


def mtu_color(*, worker):
    from src.core.stage_backends.mtu_color import ModalMtuColorBackend
    return ModalMtuColorBackend(_client(worker))


def mtu_inpaint(*, worker, model=None):
    from src.core.stage_backends.mtu_inpaint import ModalMtuInpaintBackend
    return ModalMtuInpaintBackend(_client(worker), model)


def deepseek(**options):
    from src.core.stage_backends.deepseek import DeepSeekTranslationBackend
    return DeepSeekTranslationBackend(**options)
