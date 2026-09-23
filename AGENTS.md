# Saber Translator Fork — Agent Guide

This fork is being evolved into an Agent-first manga processing backend with
replaceable compute backends and an optional browser editor. Read the
architecture authorities before changing code; the root README is a product
overview, not an implementation specification.

## Required reading order

1. `docs/README.md` — authority index and document status rules.
2. `docs/DEVELOPMENT_SETUP.md` — reproducible source setup, safe startup and
   what each verification layer actually proves.
3. `docs/ARCHITECTURE.md` — current system and approved target topology.
4. `docs/MODULE_BOUNDARIES.md` — ownership and dependency direction.
5. `docs/PIPELINE_CONTRACTS.md` — canonical page, bubble, and stage contracts.
6. `docs/UPSTREAM_MTU.md` — pinned MTU relationship and upgrade procedure.
7. `docs/STAGE_PLUGINS.md` — plugin configuration, exact ports and lifecycle;
   `docs/DEVELOPMENT_HISTORY.md` for historical rationale.
8. The narrow source files and tests for the component being changed.

Do not treat a `TARGET` or `PROPOSED` section as implemented behavior.  Verify
`CURRENT` claims against the source before relying on them.

## Product boundary

- The primary product path is headless and Agent-callable. It must be able to
  process a page without starting Vue or requiring a human editing session.
- Saber owns the optional browser editor, bookshelf/project state and future
  control-plane contracts. It does not replace MTU's native page controller.
- MTU is an upstream compute engine.  Do not copy or vendor its source into
  this repository.  Consume a pinned revision through an adapter or worker.
- Oracle is the future control/storage node, not a GPU host.  Oracle deployment
  and secrets belong to a separate operations repository, never this repo.
- `mtu_native` is the default-quality whole-page boundary. It pauses the
  pinned MTU controller only at its natural translation seam: Modal extracts
  native regions, a control-plane translation adapter translates stable region
  IDs, and Modal rehydrates those native regions before MTU mask/inpaint/render.
- `modal_mtu_deepseek` and `src/core/page_pipeline.py` are retained as an
  advanced staged-composition path. They are not the native-quality default
  and must not be used as evidence that the original MTU pipeline was
  preserved.

## Non-negotiable design rules

1. Preserve the upstream algorithm before adding abstraction. The native MTU
   path must call the pinned controller; do not reconstruct its stage order,
   masks, region semantics, inpainting behavior or renderer in Saber.
2. Module replacement means wrapping MTU's existing detector/OCR/inpainter/
   renderer seams and the external text translator seam. Default image adapters select the original MTU
   implementations. A replacement must satisfy the full MTU-native downstream
   contract, not merely return boxes and strings.
3. Keep MTU `Context`, `Quadrilateral` and `TextBlock` semantics through
   both native halves. At the translation boundary serialize the complete
   `TextBlock.to_dict()` payload plus a stable ID and raw mask. Pinned MTU
   counter-rotates `lines` in `to_dict()`; rehydration must restore their live
   orientation using its `angle` and `center` before resuming MTU.
   `BubbleState` is an optional Saber-editor projection, never the native
   intermediate state.
4. The primary caller is an Agent, CLI or future job API. Vue is an optional
   inspection/editing client and must not be required for automatic output.
5. Model/module choice and execution location are separate decisions. Changing
   OCR selects another MTU-compatible OCR adapter; changing local/Modal changes
   transport without changing page semantics.
6. The six independent Saber stage ports remain useful for extraction-only,
   typesetting-only and deliberate hybrid experiments. They must be labeled as
   staged composition and must not silently replace `mtu_native` for full-page
   quality.
7. User edits outrank generated values when an editor document is explicitly
   created. A rerun must not silently overwrite manually edited text, geometry
   or style.
8. Do not log API keys, authorization headers, signed URLs, full request bodies
   containing credentials, recognized private text, or private image contents.

## Change workflow

1. Classify the change: UI/editor, domain contract, pipeline orchestration,
   backend adapter, persistence, or deployment.
2. Read only the corresponding authority and source path from the ownership
   table in `docs/MODULE_BOUNDARIES.md`.
3. If a public contract or ownership boundary changes, update the authority
   document before or in the same commit as the implementation.
4. Make the smallest compatible change.  Preserve existing request and response
   shapes unless a versioned migration is included.
5. Add focused tests for the contract and adapter.  Do not download models or
   install a GPU stack merely to validate pure orchestration code.
6. Run the narrow tests first, then the available backend/frontend suites, and
   record any environment limitation honestly.
7. Review the complete diff for accidental generated files, absolute local
   paths, secrets, and unrelated edits.

## Verification entry points

- Pure Python contract tests: `python -m unittest tests_backend.<module>`
- Native controller wrapper tests: `python -m unittest
  tests_backend.test_native_mtu_page_engine tests_backend.test_mtu_native_runtime`
- Backend suite: use the repository's supported Python environment and
  `tests_backend/`; heavy model tests are separate from contract tests.
- Frontend unit tests: run the scripts declared in `vue-frontend/package.json`.
- Frontend production build: run the build script declared there after API or
  shared-type changes.
- Documentation gate: `python tools/validate_docs.py` after any maintained
  Markdown or documentation-index change.
- Always run `git diff --check` before committing.

If dependencies are unavailable, do not claim the affected suite passed.  A
syntax check is not a substitute for a behavior test.

## Documentation update policy

- Pipeline topology or hosting responsibility → `docs/ARCHITECTURE.md`.
- Module ownership or dependency direction → `docs/MODULE_BOUNDARIES.md`.
- Request, response, schema, overwrite, retry, or artifact semantics →
  `docs/PIPELINE_CONTRACTS.md`.
- MTU revision, imported capability, mapping, or upgrade procedure →
  `docs/UPSTREAM_MTU.md`.
- Stage plugin installation, configuration or lifecycle → `docs/STAGE_PLUGINS.md`.
- Source prerequisites, startup commands or verification layers →
  `docs/DEVELOPMENT_SETUP.md`.
- Historical rationale/milestones → `docs/DEVELOPMENT_HISTORY.md`.
- New authoritative document → add it to `docs/README.md` and remove any
  competing current authority.

Historical notes must not masquerade as current instructions.  Mark superseded
material explicitly and link to its replacement.
