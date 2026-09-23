"""Explicit registry for whole-page engines.

Whole-page engines and six-stage plugins are intentionally separate.  The
former preserve a vendor's native controller; the latter are an advanced
composition path for independently replaceable stages.
"""

from typing import Callable, Dict, Tuple

from .base import PageEngine, UnsupportedPageEngine


PageEngineFactory = Callable[[], PageEngine]
_PAGE_ENGINES: Dict[str, PageEngineFactory] = {}


def _name(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        raise ValueError("整页引擎名称不能为空")
    return normalized


def register_page_engine(name: str, factory: PageEngineFactory, *, replace: bool = False) -> None:
    normalized = _name(name)
    if normalized in _PAGE_ENGINES and not replace:
        raise ValueError(f"整页引擎已注册: {normalized}")
    if not callable(factory):
        raise TypeError("整页引擎 factory 必须可调用")
    _PAGE_ENGINES[normalized] = factory


def unregister_page_engine(name: str) -> None:
    _PAGE_ENGINES.pop(_name(name), None)


def registered_page_engines() -> Tuple[str, ...]:
    return tuple(sorted(_PAGE_ENGINES))


def create_page_engine(name: str) -> PageEngine:
    normalized = _name(name)
    factory = _PAGE_ENGINES.get(normalized)
    if factory is None:
        available = ", ".join(registered_page_engines()) or "无"
        raise UnsupportedPageEngine(
            f"未注册的整页引擎: {normalized}（可用: {available}）"
        )
    engine = factory()
    if not callable(getattr(engine, "execute", None)):
        raise TypeError(f"整页引擎 {normalized} 没有 execute")
    return engine
