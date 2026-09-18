"""Small, stage-scoped execution backend contract."""

from dataclasses import dataclass
from typing import Any, Callable, Protocol


StageCallable = Callable[..., Any]


class UnsupportedStageBackend(ValueError):
    """Raised when a selected backend is unavailable for a specific stage."""


class StageBackend(Protocol):
    """An implementation for one logical stage, not a whole pipeline."""

    name: str

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Run the stage and return its native, normalized stage result."""


@dataclass
class LocalStageBackend:
    """Preserves an existing local function behind the stage backend contract."""

    handler: StageCallable
    name: str = "local"

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.handler(*args, **kwargs)
