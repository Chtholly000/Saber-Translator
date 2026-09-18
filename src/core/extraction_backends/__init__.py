"""Execution boundary for text detection and OCR."""

from .base import ExtractionBackend, UnsupportedExtractionBackend
from .registry import (
    create_extraction_backend,
    register_extraction_backend,
    registered_extraction_backends,
    unregister_extraction_backend,
)
from .mtu_modal import (
    ModalMtuExtractionBackend,
    MtuWorkerClient,
    register_modal_mtu_extraction_backend,
)

__all__ = [
    "ExtractionBackend",
    "UnsupportedExtractionBackend",
    "create_extraction_backend",
    "register_extraction_backend",
    "registered_extraction_backends",
    "unregister_extraction_backend",
    "ModalMtuExtractionBackend",
    "MtuWorkerClient",
    "register_modal_mtu_extraction_backend",
]
