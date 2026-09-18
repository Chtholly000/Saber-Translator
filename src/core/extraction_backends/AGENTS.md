# Extraction Backend Rules

This directory is a transitional execution seam for detection and OCR.  The
root `AGENTS.md` and `docs/MODULE_BOUNDARIES.md` remain authoritative.

- Keep contracts free of Flask, Vue, filesystem sessions, vendor SDKs, and
  model imports.
- Registration must be cheap and side-effect free.  Load models and establish
  remote clients lazily.
- The built-in `local` backend must preserve the existing callable behavior.
- New adapters must normalize their output before it reaches a route.
- Never return an MTU `TextBlock`, Modal object, HTTP response, or provider SDK
  model to the application layer.
- Do not log credentials, signed artifact URLs, or image payloads.
- Add pure contract tests for registration, forwarding, errors, and result
  shape.  Add integration tests separately for heavy model behavior.
- Unsupported backends must fail explicitly; do not silently fall back to local
  execution when the user selected a remote backend.

The target architecture has stage-specific ports with shared execution clients.
Do not expand the current combined `ExtractionBackend` into a universal pipeline
backend.  When adding inpainting or rendering, introduce their own stage ports.
