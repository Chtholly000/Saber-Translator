# Processing plugin loader

Read root AGENTS.md and docs/STAGE_PLUGINS.md before changing this package.

- One registration exposes one stage, even if implementations share a worker.
- Configuration is operator-owned; never load factories from HTTP requests.
- Validate the complete composition before registration. Do not overwrite local
  or existing names, silently ignore options, or fall back after plugin failure.
- Discovery/registration must not import plugin code, load models or call APIs.
- Keep cached initialization, serialized execution and optional close lifecycle.
- Never echo factory options or raw provider exceptions in discovery/errors.
- Version incompatible port/config changes, preserve legacy extraction bridges.
- Verify all six routes, OCR-only replacement, malformed results and laziness
  with tests_backend.test_pipeline_plugins; document actual deployment separately.
