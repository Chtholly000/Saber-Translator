"""Small, stage-scoped execution backend contract."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Protocol

from src.core.ocr_types import OcrResult


StageCallable = Callable[..., Any]


class UnsupportedStageBackend(ValueError):
    """Raised when a selected backend is unavailable for a specific stage."""


class StageBackend(Protocol):
    """An implementation for one logical stage, not a whole pipeline."""

    name: str

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Run the stage and return its native, normalized stage result."""


class DetectorBackend(Protocol):
    def execute(self, image: Any, **options: Any) -> Dict[str, Any]: ...


class OcrBackend(Protocol):
    def execute(self, image: Any, bubble_coords: List[Any], **options: Any) -> List[OcrResult]: ...


class ColorBackend(Protocol):
    def execute(self, image: Any, bubble_coords: List[Any], textlines_per_bubble=None) -> List[Dict]: ...


class TranslatorBackend(Protocol):
    def execute(self, texts: List[str], *, target_language: str, prompt_content=None, **options: Any) -> List[str]: ...


class InpainterBackend(Protocol):
    def execute(self, image: Any, bubble_coords: List[Any], **options: Any) -> tuple: ...


class RendererBackend(Protocol):
    def execute(self, image: Any, bubble_states: List[Any], *, auto_font_size: bool = False) -> Any: ...


@dataclass
class LocalStageBackend:
    """Preserves an existing local function behind the stage backend contract."""

    handler: StageCallable
    name: str = "local"

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.handler(*args, **kwargs)
