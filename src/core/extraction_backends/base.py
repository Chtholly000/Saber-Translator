"""Contracts for selecting where text extraction work is executed.

Detection and OCR intentionally share one boundary because a remote worker can
reuse the decoded image and loaded models.  Translation, storage, and rendering
remain outside this contract.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Protocol


DetectionCallable = Callable[..., Dict[str, Any]]
OcrCallable = Callable[..., List[Any]]


@dataclass(frozen=True)
class LocalExtractionFunctions:
    """Existing Saber functions used by the built-in local adapter."""

    detect: DetectionCallable
    ocr: OcrCallable


class ExtractionBackend(Protocol):
    """Synchronous boundary used by the current Flask request handlers."""

    name: str

    def detect(self, image: Any, **options: Any) -> Dict[str, Any]:
        """Detect text regions in an image."""

    def ocr(
        self,
        image: Any,
        bubble_coords: List[Any],
        **options: Any,
    ) -> List[Any]:
        """Recognize text for the supplied regions."""


class UnsupportedExtractionBackend(ValueError):
    """Raised when a request selects an unregistered execution backend."""
