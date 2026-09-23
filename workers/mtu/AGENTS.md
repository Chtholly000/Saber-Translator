# MTU Worker ownership

Read the root AGENTS.md and docs/UPSTREAM_MTU.md first, then README.md here.

This directory owns only the staged/partial-processing worker. Full-page
native-quality work belongs to `workers/mtu_native/`; do not expand this narrow
worker into a second whole-page controller.

- `runtime.py` is the only place that imports MTU stage implementations.
- Use narrow detection/OCR/inpainting/merge dispatchers, never MangaTranslator.
- Model names/options come from server configuration, not browser-local models.
- Keep image coordinates in original pixels, preserve OCR request IDs and line
  order, and fail on malformed output. Empty recognized text is legitimate.
- Importing modules, registering profiles and constructing clients must not
  load models, download weights, read credentials or make remote calls.
- `modal_app.py` is a deployment recipe, not an automatic startup action.
- Fixture tests do not demonstrate real GPU quality, cold-start performance,
  image build success, or model license clearance. Record these separately.
- Validate with `tests_backend.test_remote_pipeline` and the existing contract
  suites before changing the protocol. Incompatible changes need a new version.
- Do not commit model weights, user images, credentials or generated build files.
