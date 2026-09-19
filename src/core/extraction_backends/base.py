"""Legacy combined extraction API, retained for existing integrations.

New implementations use independent DetectorBackend/OcrBackend execute ports
from stage_backends. Sharing a worker does not require sharing a stage interface.
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
