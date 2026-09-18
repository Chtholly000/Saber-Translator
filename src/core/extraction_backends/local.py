"""Adapter for Saber's existing in-process detection and OCR functions."""

from typing import Any, Dict, List

from .base import LocalExtractionFunctions


class LocalExtractionBackend:
    name = "local"

    def __init__(self, functions: LocalExtractionFunctions):
        self._functions = functions

    def detect(self, image: Any, **options: Any) -> Dict[str, Any]:
        return self._functions.detect(image, **options)

    def ocr(
        self,
        image: Any,
        bubble_coords: List[Any],
        **options: Any,
    ) -> List[Any]:
        return self._functions.ocr(image, bubble_coords, **options)
