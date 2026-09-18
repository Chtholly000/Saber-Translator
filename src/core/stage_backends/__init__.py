"""Stage-scoped backend registry public API."""

from .base import StageBackend, UnsupportedStageBackend
from .registry import (
    create_stage_backend,
    register_stage_backend,
    registered_stage_backends,
    unregister_stage_backend,
)

__all__ = [
    "StageBackend",
    "UnsupportedStageBackend",
    "create_stage_backend",
    "register_stage_backend",
    "registered_stage_backends",
    "unregister_stage_backend",
]
