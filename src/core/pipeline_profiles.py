"""Execution-profile selection for the automatic translation pipeline.

A profile chooses *where/which adapter* each stage uses. It deliberately does
not contain model settings, credentials, UI state, or a workflow definition:
those belong respectively to a stage adapter, secret/configuration layer, a
presentation client, and the pipeline controller.

Only ``local_saber`` is registered today. This is intentional: an unavailable
remote profile must fail during selection instead of silently running locally.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Mapping, Optional, Tuple


PIPELINE_STAGES: Tuple[str, ...] = (
    "detect",
    "ocr",
    "translate",
    "inpaint",
    "render",
)


class UnsupportedPipelineProfile(ValueError):
    """Raised when a requested execution profile or stage is not registered."""


@dataclass(frozen=True)
class PipelineProfile:
    """Complete backend selection for one automatic pipeline run."""

    name: str
    stage_backends: Mapping[str, str]

    def backend_for(self, stage: str) -> str:
        normalized_stage = _normalize_stage(stage)
        backend = self.stage_backends.get(normalized_stage)
        if not backend:
            raise UnsupportedPipelineProfile(
                f"执行 profile {self.name} 未配置阶段: {normalized_stage}"
            )
        return _normalize_backend_name(backend)


def _normalize_profile_name(name: Optional[str]) -> str:
    normalized = str(name or "local_saber").strip().lower().replace("-", "_")
    return normalized or "local_saber"


def _normalize_stage(stage: str) -> str:
    normalized = str(stage or "").strip().lower().replace("-", "_")
    if normalized not in PIPELINE_STAGES:
        available = ", ".join(PIPELINE_STAGES)
        raise UnsupportedPipelineProfile(
            f"未知流水线阶段: {normalized or '<empty>'}（可用: {available}）"
        )
    return normalized


def _normalize_backend_name(name: str) -> str:
    normalized = str(name or "").strip().lower().replace("-", "_")
    if not normalized:
        raise UnsupportedPipelineProfile("阶段后端名称不能为空")
    return normalized


def _profile(name: str, **stage_backends: str) -> PipelineProfile:
    normalized_backends = {
        _normalize_stage(stage): _normalize_backend_name(backend)
        for stage, backend in stage_backends.items()
    }
    missing = sorted(set(PIPELINE_STAGES) - set(normalized_backends))
    if missing:
        raise ValueError(f"profile {name} 缺少阶段: {', '.join(missing)}")
    return PipelineProfile(
        name=_normalize_profile_name(name),
        stage_backends=MappingProxyType(normalized_backends),
    )


_PIPELINE_PROFILES: Dict[str, PipelineProfile] = {
    "local_saber": _profile(
        "local_saber",
        detect="local",
        ocr="local",
        translate="local",
        inpaint="local",
        render="local",
    ),
}


def register_pipeline_profile(
    name: str,
    stage_backends: Mapping[str, str],
    *,
    replace: bool = False,
) -> None:
    """Register a complete profile during application/bootstrap setup.

    Registration is deliberately data-only. It must not instantiate model
    adapters or establish a remote connection; the individual stage registries
    remain responsible for that lazy work.
    """

    normalized_name = _normalize_profile_name(name)
    if normalized_name in _PIPELINE_PROFILES and not replace:
        raise ValueError(f"流水线 profile 已注册: {normalized_name}")
    _PIPELINE_PROFILES[normalized_name] = _profile(
        normalized_name,
        **dict(stage_backends),
    )


def unregister_pipeline_profile(name: str) -> None:
    """Remove a non-built-in profile, primarily for reloads and tests."""

    normalized_name = _normalize_profile_name(name)
    if normalized_name == "local_saber":
        raise ValueError("不能注销内置 local_saber 流水线 profile")
    _PIPELINE_PROFILES.pop(normalized_name, None)


def get_pipeline_profile(name: Optional[str] = None) -> PipelineProfile:
    """Return a complete registered profile without loading any model/client."""

    normalized = _normalize_profile_name(name)
    profile = _PIPELINE_PROFILES.get(normalized)
    if profile is None:
        available = ", ".join(registered_pipeline_profiles()) or "无"
        raise UnsupportedPipelineProfile(
            f"未注册的流水线 profile: {normalized}（可用: {available}）"
        )
    return profile


def registered_pipeline_profiles() -> Tuple[str, ...]:
    """Return stable profile names suitable for configuration validation."""

    return tuple(sorted(_PIPELINE_PROFILES))


def resolve_stage_backend(
    profile_name: Optional[str],
    stage: str,
    *,
    backend_override: Optional[str] = None,
) -> Tuple[PipelineProfile, str]:
    """Resolve one stage's adapter name, with an explicit request override.

    The override is a narrow migration hook for a stage-specific adapter. It
    never creates or falls back to a backend: the relevant stage registry still
    decides whether that name is actually available.
    """

    profile = get_pipeline_profile(profile_name)
    configured_backend = profile.backend_for(stage)
    if backend_override is None:
        return profile, configured_backend
    return profile, _normalize_backend_name(backend_override)


def resolve_stage_backend_request(
    profile_name: Optional[str],
    stage: str,
    *,
    stage_backend: Optional[str] = None,
    legacy_backend: Optional[str] = None,
) -> Tuple[PipelineProfile, str]:
    """Resolve a stage request while validating the extraction migration fields."""

    if stage_backend and legacy_backend:
        normalized_stage = _normalize_backend_name(stage_backend)
        normalized_legacy = _normalize_backend_name(legacy_backend)
        if normalized_stage != normalized_legacy:
            raise ValueError(
                "阶段专用后端与 extraction_backend 不能选择不同后端"
            )
    return resolve_stage_backend(
        profile_name,
        stage,
        backend_override=stage_backend or legacy_backend,
    )
