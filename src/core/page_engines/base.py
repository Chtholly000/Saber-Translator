"""Agent-facing result contract for one complete page-processing engine.

The engine result deliberately does not depend on Saber's editor model. A
native engine keeps its own rich document until an optional editor adapter is
asked to project it into an editor-specific shape.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from PIL import Image


class UnsupportedPageEngine(ValueError):
    """Raised when a requested whole-page engine is not registered."""


@dataclass
class PageEngineResult:
    engine: str
    clean_image: Image.Image
    final_image: Image.Image
    repair_mask: Optional[Image.Image] = None
    native_document: Dict[str, Any] = field(default_factory=dict)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_document(self, *, artifacts=None) -> Dict[str, Any]:
        return {
            "pageEngineContractVersion": 1,
            "pageEngine": self.engine,
            "artifacts": dict(artifacts or {}),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "nativeDocument": dict(self.native_document),
        }


class PageEngine(Protocol):
    name: str

    def execute(self, image: Image.Image, **options: Any) -> PageEngineResult:
        """Run a complete upstream page pipeline without reimplementing its stages."""
