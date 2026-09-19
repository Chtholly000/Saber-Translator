"""Validate configured plugins/profiles without importing or executing plugins."""

import argparse
import json
from pathlib import Path

from src.core.pipeline_plugins import configure_pipeline_plugins
from src.core.pipeline_profiles import get_pipeline_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugins-config", required=True, type=Path)
    parser.add_argument("--config", type=Path, help="Optional legacy MTU remote config to extend")
    args = parser.parse_args()
    if args.config:
        from src.core.remote_bootstrap import configure_remote_backends
        with args.config.open(encoding="utf-8") as handle:
            configure_remote_backends(json.load(handle))
    with args.plugins_config.open(encoding="utf-8") as handle:
        installation = configure_pipeline_plugins(json.load(handle))
    try:
        print(json.dumps({"configured_profiles": {
            name: dict(get_pipeline_profile(name).stage_backends)
            for name in installation.profiles
        }, "plugins_executed": False}, ensure_ascii=False, indent=2))
    finally:
        installation.close()


if __name__ == "__main__":
    main()
