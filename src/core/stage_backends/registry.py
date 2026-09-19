"""Independent registries for all six processing stages."""

from typing import Callable, Dict, Optional, Tuple

from .base import (
    LocalStageBackend,
    StageBackend,
    StageCallable,
    UnsupportedStageBackend,
)


StageBackendFactory = Callable[[StageCallable], StageBackend]
STAGE_BACKEND_STAGES: Tuple[str, ...] = ("detect", "ocr", "color", "translate", "inpaint", "render")
_STAGE_BACKEND_FACTORIES: Dict[str, Dict[str, StageBackendFactory]] = {
    stage: {} for stage in STAGE_BACKEND_STAGES
}


def _normalize_stage(stage: str) -> str:
    normalized = str(stage or "").strip().lower().replace("-", "_")
    if normalized not in _STAGE_BACKEND_FACTORIES:
        available = ", ".join(STAGE_BACKEND_STAGES)
        raise ValueError(f"未知流水线阶段: {normalized or '<empty>'}（可用: {available}）")
    return normalized


def _normalize_backend_name(name: Optional[str]) -> str:
    normalized = str(name or "local").strip().lower().replace("-", "_")
    return normalized or "local"


def _local_factory(local_handler: StageCallable) -> StageBackend:
    return LocalStageBackend(local_handler)


def register_stage_backend(
    stage: str,
    name: str,
    factory: StageBackendFactory,
    *,
    replace: bool = False,
) -> None:
    """Register one stage implementation without loading models or clients."""

    normalized_stage = _normalize_stage(stage)
    normalized_name = _normalize_backend_name(name)
    factories = _STAGE_BACKEND_FACTORIES[normalized_stage]
    if normalized_name in factories and not replace:
        raise ValueError(f"阶段后端已注册: {normalized_stage}/{normalized_name}")
    factories[normalized_name] = factory


def unregister_stage_backend(stage: str, name: str) -> None:
    """Remove a non-local stage backend, primarily for reloads and tests."""

    normalized_stage = _normalize_stage(stage)
    normalized_name = _normalize_backend_name(name)
    if normalized_name == "local":
        raise ValueError("不能注销内置 local 阶段后端")
    _STAGE_BACKEND_FACTORIES[normalized_stage].pop(normalized_name, None)


def registered_stage_backends(stage: str) -> Tuple[str, ...]:
    """Return registered adapter names for exactly one logical stage."""

    return tuple(sorted(_STAGE_BACKEND_FACTORIES[_normalize_stage(stage)]))


def create_stage_backend(
    stage: str,
    name: Optional[str],
    *,
    local_handler: StageCallable,
) -> StageBackend:
    """Resolve a stage-specific adapter while retaining the current local call."""

    normalized_stage = _normalize_stage(stage)
    normalized_name = _normalize_backend_name(name)
    factory = _STAGE_BACKEND_FACTORIES[normalized_stage].get(normalized_name)
    if factory is None:
        available = ", ".join(registered_stage_backends(normalized_stage)) or "无"
        raise UnsupportedStageBackend(
            f"未注册的阶段后端: {normalized_stage}/{normalized_name}（可用: {available}）"
        )
    return factory(local_handler)


for _stage in STAGE_BACKEND_STAGES:
    register_stage_backend(_stage, "local", _local_factory)
