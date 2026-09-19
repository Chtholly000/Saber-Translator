# Saber Translator Fork — Agent Guide

This fork is being evolved into a browser-first manga typesetting application
with replaceable compute backends.  Read the architecture authorities before
changing code; the root README is a product overview, not an implementation
specification.

## Required reading order

1. `docs/README.md` — authority index and document status rules.
2. `docs/ARCHITECTURE.md` — current system and approved target topology.
3. `docs/MODULE_BOUNDARIES.md` — ownership and dependency direction.
4. `docs/PIPELINE_CONTRACTS.md` — canonical page, bubble, and stage contracts.
5. `docs/UPSTREAM_MTU.md` — pinned MTU relationship and upgrade procedure.
6. `docs/STAGE_PLUGINS.md` — plugin configuration, exact ports and lifecycle;
   `docs/DEVELOPMENT_HISTORY.md` for historical rationale.
7. The narrow source files and tests for the component being changed.

Do not treat a `TARGET` or `PROPOSED` section as implemented behavior.  Verify
`CURRENT` claims against the source before relying on them.

## Product boundary

- Saber owns the browser UI, precise text editing, bookshelf/project state,
  pipeline orchestration, and persistence contracts.
- MTU is an upstream compute engine.  Do not copy or vendor its source into
  this repository.  Consume a pinned revision through an adapter or worker.
- Oracle is the future control/storage node, not a GPU host.  Oracle deployment
  and secrets belong to a separate operations repository, never this repo.
- `modal_mtu_deepseek` is an opt-in remote composition: the pinned MTU Worker
  recipe handles GPU stages, DeepSeek handles text translation, and Saber keeps
  rendering/project state. It is not deployed or live-GPU-verified merely
  because the profile is configured. Neither provider is the canonical owner
  of project state.

## Non-negotiable design rules

1. The pipeline is a set of optional stages, not one mandatory end-to-end
   function.  Typesetting-only work must not require detection, OCR, translation,
   or inpainting.
2. `BubbleState` and the persisted page/project document are the product's
   durable contract.  Model-specific objects must be converted at adapter
   boundaries.
3. User edits outrank generated values.  A rerun must not silently overwrite
   manually edited text, geometry, or style.
4. Routes and Vue step functions orchestrate contracts; they must not import a
   vendor model implementation directly.
5. Stage ports describe capabilities (`detect`, `ocr`, optional `color`,
   `translate`, `inpaint`, `render`). Execution adapters describe where/how
   they run (`local`, `modal`, `api`). Do not combine those two decisions in UI
   components.
6. Processing plugins implement independent stage ports via explicit server
   configuration. Legacy before/after hooks remain middleware around those ports.
   Neither mechanism is a durable job protocol. New models must not require
   route changes or a combined detect/OCR implementation.
7. Keep the existing local behavior as the default until a remote adapter has
   contract tests and an explicit configuration path.
8. Do not log API keys, authorization headers, signed URLs, full request bodies
   containing credentials, or private image contents.

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
- Backend suite: use the repository's supported Python environment and
  `tests_backend/`; heavy model tests are separate from contract tests.
- Frontend unit tests: run the scripts declared in `vue-frontend/package.json`.
- Frontend production build: run the build script declared there after API or
  shared-type changes.
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
- Historical rationale/milestones → `docs/DEVELOPMENT_HISTORY.md`.
- New authoritative document → add it to `docs/README.md` and remove any
  competing current authority.

Historical notes must not masquerade as current instructions.  Mark superseded
material explicitly and link to its replacement.
