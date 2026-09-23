# Native MTU Worker ownership

Read the root `AGENTS.md`, `docs/ARCHITECTURE.md`, and
`docs/UPSTREAM_MTU.md` before changing this directory.

- This worker wraps the pinned upstream `MangaTranslator` controller. Do not
  copy, rewrite, or manually reproduce MTU detection, OCR, mask refinement,
  inpainting, layout, or rendering algorithms here.
- The only intentional pause is MTU's translation seam. `extract_page` and
  bounded `extract_pages`
  serializes complete `TextBlock.to_dict()` records with stable IDs and the
  raw mask; `render_page` and bounded `render_pages` rehydrate them, inject
  ID-matched translations,
  and resumes the original controller completion path.
- Image-module choices map to the pinned MTU `Config` groups. Execution
  location (Modal) is separate from detector/OCR/inpainter/renderer selection.
- Translation providers and credentials belong to the control plane, not this
  GPU worker. Reject credentials in request payloads and never log their values.
- Capturing clean image and mask may observe/copy controller state; it must not
  change stage order or replace controller methods with new algorithms.
- Import and registration must not load weights, read credentials, deploy an
  app, or make a network request.
- Contract changes require a version bump, focused fixture tests, and updates
  to the architecture authorities.
