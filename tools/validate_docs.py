"""Deterministic checks for maintained Markdown documentation."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
EXPLICIT_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "vue-frontend" / "README.md",
    ROOT / "workers" / "mtu" / "AGENTS.md",
    ROOT / "workers" / "mtu" / "README.md",
    ROOT / "pipeline_plugins" / "AGENTS.md",
)
REQUIRED_AUTHORITIES = {
    "ARCHITECTURE.md",
    "DEVELOPMENT_HISTORY.md",
    "DEVELOPMENT_SETUP.md",
    "MODULE_BOUNDARIES.md",
    "PIPELINE_CONTRACTS.md",
    "STAGE_PLUGINS.md",
    "UPSTREAM_MTU.md",
}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_LINK_RE = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']", re.IGNORECASE)
PERSONAL_PATH_RE = re.compile(
    r"(?:/[A-Za-z]:/Users/|[A-Za-z]:\\Users\\|/Users/[^/\s]+/|/home/[^/\s]+/)"
)


def maintained_docs() -> list[Path]:
    return sorted({*EXPLICIT_DOCS, *(ROOT / "docs").glob("*.md")})


def local_target(raw: str) -> str | None:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    return unquote(target.split("#", 1)[0])


def validate() -> list[str]:
    errors: list[str] = []
    docs = maintained_docs()
    for path in docs:
        if not path.is_file():
            errors.append(f"missing maintained document: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if path.parent == ROOT / "docs" and "状态：" not in "\n".join(text.splitlines()[:8]):
            errors.append(f"{path.relative_to(ROOT)}: missing status marker near document start")
        for match in PERSONAL_PATH_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{path.relative_to(ROOT)}:{line}: personal absolute path: {match.group(0)}"
            )
        for match in (*LINK_RE.finditer(text), *HTML_LINK_RE.finditer(text)):
            target = local_target(match.group(1))
            if target is None:
                continue
            line = text.count("\n", 0, match.start()) + 1
            if target.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", target):
                errors.append(
                    f"{path.relative_to(ROOT)}:{line}: local link must be relative: {target}"
                )
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append(
                    f"{path.relative_to(ROOT)}:{line}: local link escapes repository: {target}"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"{path.relative_to(ROOT)}:{line}: broken local link: {target}"
                )

    index = ROOT / "docs" / "README.md"
    index_text = index.read_text(encoding="utf-8") if index.is_file() else ""
    for name in sorted(REQUIRED_AUTHORITIES):
        if not (ROOT / "docs" / name).is_file():
            errors.append(f"missing required authority: docs/{name}")
        if f"{name}]" not in index_text:
            errors.append(f"docs/README.md does not index {name}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("documentation validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"documentation validation passed ({len(maintained_docs())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
