"""Whole-page engines that preserve an upstream processor's native pipeline."""

from .base import PageEngine, PageEngineResult, UnsupportedPageEngine
from .mtu_native import NativeMtuPageEngine
from .registry import (
    create_page_engine,
    register_page_engine,
    registered_page_engines,
    unregister_page_engine,
)

__all__ = [
    "NativeMtuPageEngine",
    "PageEngine",
    "PageEngineResult",
    "UnsupportedPageEngine",
    "create_page_engine",
    "register_page_engine",
    "registered_page_engines",
    "unregister_page_engine",
]
