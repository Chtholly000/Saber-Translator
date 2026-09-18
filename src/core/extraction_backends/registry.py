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
    _BACKEND_FACTORIES[normalized] = factory


def unregister_extraction_backend(name: str) -> None:
    """Remove a non-built-in backend, primarily for app reloads and tests."""

    normalized = _normalize_name(name)
    if normalized == "local":
        raise ValueError("不能注销内置 local 提取后端")
    _BACKEND_FACTORIES.pop(normalized, None)


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
