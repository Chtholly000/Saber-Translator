# MTU Worker and independent clients

Status: CURRENT implementation. The Modal image was deployed and one public
vertical-page detect/OCR smoke test passed on 2026-09-19. The four OCR strings
from that page also passed an isolated live DeepSeek translation smoke test on
2026-09-20. Color, inpaint, the combined Flask/browser flow, Oracle deployment
and a broad model-quality suite are NOT verified.

## Composition

`src/core/remote_bootstrap.py` registers `modal_mtu_deepseek` only when given an
explicit configuration. The normal `local_saber` default stays available.

Alternatively, `SABER_PIPELINE_CONFIG` selects independent factories for each
stage; `pipeline_plugins/mtu.example.json` demonstrates replacing only OCR while
keeping the other stages. See [stage plugins](../../docs/STAGE_PLUGINS.md) for
configuration, templates and the legacy registration compatibility bridge.

| Stage | Implementation | Execution |
| --- | --- | --- |
| detect | pinned MTU detector + textline merger | Modal |
| OCR | pinned MTU 32px / 48px / 48px_ctc / mocr | Modal |
| color (optional stage) | pinned MTU 48px colors | Modal |
| translate | `stage_backends/deepseek.py`, stable text IDs | DeepSeek official API |
| inpaint | pinned MTU lama_mpe / lama_large / default | Modal |
| render | existing Saber renderer | application CPU |

The optional color stage is explicitly configured so the automatic pipeline does
not accidentally start a local 48px model. `solid` inpainting is an explicit CPU
fill operation; it is never a fallback for failed GPU inpainting. User brush
black pixels preserve content and white pixels request repair, even outside
detected boxes. Mask dilation uses a square radius in this adapter; the legacy
Saber mask implementation uses an ellipse.

The browser's More / parallel settings panel lists profiles from
`GET /api/parallel/profiles`. Listing means configured, not cloud health-checked.
The remote profile owns its models in server configuration; browser-local OCR,
detector/refinement and translation-provider settings do not select remote models.
Font/layout and mask/brush settings still apply. Ordinary whole-page translation
and remove-text modes are supported. Legacy HQ, proofread and single-bubble
translation flows explicitly reject remote profiles. Optional glossary extraction
still uses its existing separately configured API path.

## Configuration

Start from `config.example.json` and set the operator's deployed Modal app name,
MTU model options and desired DeepSeek model. The current example uses
`deepseek-flash` at `https://api.deepseek.com`, disables thinking for this bounded
JSON translation request, and expects the key in server environment variable
`DEEPSEEK_API_KEY`. The file accepts no API keys or arbitrary HTTP destination.
`api_key_env` only names that environment variable; the adapter resolves its value
at execution and sends only texts/prompt to DeepSeek. The Modal SDK uses its
standard operator credentials; neither provider's credentials enter Worker
payloads or browser profile discovery.

Set `SABER_REMOTE_CONFIG` to the non-secret configuration file when starting the
existing Saber app. No configuration means no remote profile. Registration itself
does not connect to Modal or DeepSeek. Invalid configuration fails startup.
The Worker contract rejects images above 40,000,000 pixels or 48 MiB of encoded
PNG data before dispatch, rather than sending an unbounded page to a GPU.

The current full `app.py` still has legacy modules that require the existing
Saber environment. The atomic routes use lazy local-model handlers, but this is
NOT yet a GPU-dependency-free Oracle application package.

## Worker build and execution boundary

`modal_app.py` pins MTU revision `f0307a063214f915f2b1d6e5cd3233f3bf78339f` and
uses that revision's `uv.lock` with the CUDA 12.6 dependency group. Upstream
dependencies remain confined to the worker image. Runtime graphics/font libraries
required by MTU's text-block construction are explicit in the recipe and kept in a
small layer after the large CUDA dependency layer.

The recipe was built and deployed with Modal SDK 1.5.5 as
`saber-mtu-f0307a0` on 2026-09-19. Deployment is external state, so a future
operator must still confirm that the named app exists before relying on it. To
deploy or update it after cost and model-license review:

```sh
python -m pip install -r requirements-remote.txt
modal deploy -m workers.mtu.modal_app
```

This explicitly deploys one L4 container maximum, with zero warm containers and a
60-second scale-down window. There is no public HTTP endpoint, durable image store,
or persistent model volume. Weights are loaded/downloaded on first invocation and
can be reused while that container lives; cold starts may repeat downloads. Add a
bounded cache only after reviewing model licenses and storage cost/ownership.

Calls are synchronous and have no automatic adapter retry, durable job ID,
cancellation propagation or idempotent page writeback. Cold starts can exceed an
HTTP proxy/browser timeout. Validate from a direct client first; do not describe
this as production Oracle/Cloudflare deployment readiness.

Official SDK references: [authenticated deployed class lookup](https://modal.com/docs/guide/trigger-deployed-functions),
[container lifecycle](https://modal.com/docs/guide/lifecycle-functions),
[image construction](https://modal.com/docs/guide/images).

### Live GPU smoke test (2026-09-19)

The deployed class was called directly with upstream's public `pic/before2.png`
sample. That file contains JPEG bytes despite its suffix, so the test re-encoded
the same 3065×4096 RGB page as a real PNG before sending it through the contract.
The request used the default detector at detection size 1536 followed by the MTU
48px OCR engine.

- Detect returned four regions, all vertical, and a full-size text mask.
- OCR returned four ID-aligned results with non-empty Japanese text; reported
  confidence ranged from 0.6856 to 0.9992.
- Cold-path wall time was 45.285 seconds for detect and 35.326 seconds for OCR,
  80.612 seconds total.
- The Modal monthly summary immediately afterward showed USD 0.18 metered and
  USD 0 billed because credits covered it. This is the aggregate for the build,
  CPU probes, failed compatibility probes and successful GPU run, not a stable
  per-page quote.

This proves deployed-class lookup, L4 startup, weight download, detector,
textline merge, PNG mask transport and 48px OCR for that one page. It does not
prove general recognition quality, all document orientations, color extraction,
inpainting, the complete Flask/browser flow, persistent model caching or Oracle
readiness.

### Live DeepSeek translation smoke test (2026-09-20)

The DeepSeek stage adapter was called directly with the same four public Japanese
OCR strings produced by the GPU smoke test, targeting Simplified Chinese with
`deepseek-flash`. It returned four non-empty translations aligned to the original
stable IDs in 2.029 seconds. The request used non-streaming JSON mode with thinking
disabled; the dedicated key was supplied only through the process environment and
was not placed in configuration, payloads, logs or the browser.

This proves the current official endpoint/model combination and the adapter's
ID-preserving live request/response path for one small batch. It does not prove
translation quality at scale, retry/rate-limit behavior, the combined Modal plus
DeepSeek pipeline, browser writeback or Oracle deployment.

## Independent clients

These clients use the same stage ports without starting Flask or the UI.
Outputs must use new paths; existing files are never overwritten.

Extract text without translating or rendering (the DeepSeek key is not used):

```sh
python -m tools.extract_text --image page.png --output extracted.json --config remote-config.json
```

Typeset an existing or AI-generated blank image without OCR, detection,
translation, inpainting or cloud access:

```sh
python -m tools.typeset --image blank.png --layout captions.json --output lettered.png
```

Both clients also accept `--plugins-config pipeline.json --profile chosen_name`
to select configured stage plugins. Typesetting initializes only the render plugin.

`captions.json` contains existing `BubbleState` fields. An AI client can generate
the layout as data; the command requires no manual editing UI:

```json
{"bubble_states": [{
  "bubbleId": "caption-1", "coords": [20, 20, 380, 140],
  "translatedText": "你好，世界", "textDirection": "horizontal",
  "fontFamily": "fonts/Arial_Unicode.ttf", "fontSize": 30
}]}
```

The CLI selects the `render` port, so a later renderer adapter can replace the
algorithm without changing this JSON or the editor. Generating the placement
coordinates automatically from the picture is a separate, not-yet-implemented
layout capability.

## Verification

```sh
python -m unittest tests_backend.test_deepseek_adapter tests_backend.test_pipeline_plugins tests_backend.test_remote_pipeline tests_backend.test_typeset_client tests_backend.test_mtu_worker_adapter tests_backend.test_pipeline_profiles tests_backend.test_stage_backend_registry tests_backend.test_extraction_backend_boundary
```

Fixtures execute real Flask handlers, real adapters, the Worker dispatcher and
actual vendor-object normalization using injected model dispatch functions. The
repeatable test suite mocks DeepSeek HTTP transport; the bounded live adapter
check is recorded separately above. Fixtures cover reversed/missing IDs, rotated
geometry, empty OCR, image/mask sizes, credential isolation, brush-only repair,
no local GPU fallback, and blank-image rendering with the real Saber renderer.
The single live vertical-page smoke test above adds a real GPU compatibility
check, but does not establish general model quality. Before production-like use,
run horizontal, rotated, empty-page and complex-background fixtures on the pinned
models and separately exercise color and inpaint.
