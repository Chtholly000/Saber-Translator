"""Small registry for local and externally hosted extraction backends."""

from typing import Callable, Dict, Optional, Tuple

from .base import (
    DetectionCallable,
    ExtractionBackend,
    LocalExtractionFunctions,
    OcrCallable,
    UnsupportedExtractionBackend,
)
from .local import LocalExtractionBackend
from src.core.stage_backends import (
    register_stage_backend, registered_stage_backends, unregister_stage_backend,
)
from src.core.stage_backends.base import LocalStageBackend


BackendFactory = Callable[[LocalExtractionFunctions], ExtractionBackend]
_BACKEND_FACTORIES: Dict[str, BackendFactory] = {}


def _normalize_name(name: Optional[str]) -> str:
    normalized = str(name or "local").strip().lower().replace("-", "_")
    return normalized or "local"


def register_extraction_backend(
    name: str,
    factory: BackendFactory,
    *,
    replace: bool = False,
) -> None:
    """Register a backend factory without importing GPU or HTTP dependencies."""

    normalized = _normalize_name(name)
    if normalized in _BACKEND_FACTORIES and not replace:
        raise ValueError(f"提取后端已注册: {normalized}")
    if normalized != "local":
        # Legacy registrations become two independent ports. New plugins only
        # implement the stage they provide; this bridge is for older callers.
        if not replace and any(normalized in registered_stage_backends(stage) for stage in ("detect", "ocr")):
            raise ValueError(f"阶段后端已注册: {normalized}")

        def bridge(stage):
            def make(local_handler):
                def unused(*args, **kwargs):
                    raise RuntimeError("旧提取后端不能从一个阶段隐式调用另一个阶段")
                functions = LocalExtractionFunctions(
                    detect=local_handler if stage == "detect" else unused,
                    ocr=local_handler if stage == "ocr" else unused,
                )
                return LocalStageBackend(getattr(factory(functions), stage), name=normalized)
            return make

        for stage in ("detect", "ocr"):
            register_stage_backend(stage, normalized, bridge(stage), replace=replace)
    _BACKEND_FACTORIES[normalized] = factory


def unregister_extraction_backend(name: str) -> None:
    """Remove a non-built-in backend, primarily for app reloads and tests."""

    normalized = _normalize_name(name)
    if normalized == "local":
        raise ValueError("不能注销内置 local 提取后端")
    if _BACKEND_FACTORIES.pop(normalized, None) is not None:
        for stage in ("detect", "ocr"):
            unregister_stage_backend(stage, normalized)


def registered_extraction_backends() -> Tuple[str, ...]:
    return tuple(sorted(_BACKEND_FACTORIES))


def create_extraction_backend(
    name: Optional[str],
    *,
    local_detect: DetectionCallable,
    local_ocr: OcrCallable,
) -> ExtractionBackend:
    """Resolve a request backend while keeping the existing local path intact."""

    normalized = _normalize_name(name)
    factory = _BACKEND_FACTORIES.get(normalized)
    if factory is None:
        available = ", ".join(registered_extraction_backends()) or "无"
        raise UnsupportedExtractionBackend(
            f"未注册的提取后端: {normalized}（可用: {available}）"
        )
    return factory(LocalExtractionFunctions(detect=local_detect, ocr=local_ocr))


register_extraction_backend("local", LocalExtractionBackend)
