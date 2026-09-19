"""Public entry point for trusted, server-configured processing plugins."""

from .loader import configure_pipeline_plugins, configure_pipeline_plugins_from_env

__all__ = ["configure_pipeline_plugins", "configure_pipeline_plugins_from_env"]
