"""Stage-scoped backend registry public API."""

from .base import (
    StageBackend, UnsupportedStageBackend, DetectorBackend, OcrBackend,
    ColorBackend, TranslatorBackend, InpainterBackend, RendererBackend,
)
from .registry import (
    create_stage_backend,
    register_stage_backend,
    registered_stage_backends,
    unregister_stage_backend,
)

__all__ = [
    "StageBackend",
    "DetectorBackend", "OcrBackend", "ColorBackend",
    "TranslatorBackend", "InpainterBackend", "RendererBackend",
    "UnsupportedStageBackend",
    "create_stage_backend",
    "register_stage_backend",
    "registered_stage_backends",
    "unregister_stage_backend",
]
