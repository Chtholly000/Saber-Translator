# Native MTU split worker

Status: `CURRENT` for the v3 split/batch contract, focused tests, and the
recorded two-page Modal L4 smoke test. Deployment remains explicit and
environment-specific.

This is the default-quality headless integration boundary. It does not use Vue
or require a person to edit a page. It pauses the pinned MTU controller only at
the translation seam:

```text
extract_page / extract_pages
  MTU detection → OCR → textline merge
  → stable IDs + full TextBlock data + raw mask

control plane
  replaceable Translator adapter
  → translations keyed by stable ID

render_page / render_pages
  rehydrate MTU TextBlock
  → MTU mask refinement → inpainting → rendering
```

The worker never converts native regions to `BubbleState` and does not
reimplement MTU algorithms.

## What is replaceable

- `page.detector` and `page.ocr` select MTU-compatible extraction modules.
- `translation.backend` selects a control-plane text translator. The example
  uses DeepSeek; another adapter can implement the same
  `execute(texts, target_language, prompt_content)` interface.
- `page.inpainter` and `page.render` select MTU-compatible completion modules.
- `worker` selects execution transport. Modal is current, but the page engine
  does not depend on Modal-specific response objects.

A new OCR implementation must produce the full MTU-native downstream semantics,
not only boxes and strings. A new translator only sees ordered text and returns
the same number of strings; stable region IDs prevent translations from being
written to the wrong region.

## Credentials and deployment

The Modal worker has no DeepSeek Secret and never calls a translation API.
`DEEPSEEK_API_KEY` belongs to the control process environment (later the
Oracle secret boundary). Do not place its value in JSON, command arguments,
Git, task artifacts, or chat.
The native page engine checks the selected translator's readiness before any
Modal extraction call. With DeepSeek selected, a missing key fails immediately
instead of spending GPU time and failing only after OCR.

Deploying the image worker is a deliberate external action:

```sh
modal deploy -m workers.mtu_native.modal_app
```

The recipe pins MTU revision
`f0307a063214f915f2b1d6e5cd3233f3bf78339f`, uses an L4 GPU, scales to zero,
and limits the app to one container. Deployment and calls may incur Modal cost.

## Agent-facing use

After deploying the worker and placing the translation credential in the
control process environment:

```sh
python -m tools.translate_page_native \
  --image page-001.png \
  --image page-002.png \
  --output-dir result-batch \
  --config workers/mtu_native/config.example.json
```

For multiple inputs, the command groups up to four pages per extract/render
Worker call and makes one translation-adapter call for all extracted regions.
It atomically publishes `batch.json` plus one output directory per page. A
single input keeps the original `final.png`, `clean.png`, `mask.png`, and
`page.json` layout. The optional Saber editor is not part of execution.

## Batch tuning and later changes

The default is deliberately conservative: four pages per GPU call, with a
hard wire limit of eight. Both values are defined beside the versioned
contract in `src/core/native_mtu_page_contract.py` as
`DEFAULT_NATIVE_MTU_GPU_BATCH_PAGES` and `MAX_NATIVE_MTU_BATCH_PAGES`. The CLI
uses the same constants, so ordinary experiments need only
`--gpu-batch-size 1..8`; no code edit or redeploy is needed.

`gpu_batch_size` changes only how many pages are placed in each Modal
`extract_pages` / `render_pages` call. `execute_batch` currently flattens every
region from all submitted pages into one control-plane Translator call. Modal
still processes pages sequentially inside the same warm container, preserving
one isolated MTU Context/TextBlock set per page while reusing loaded models.

If evidence later justifies raising the hard limit, change the two constants
above, update the bound tests and this documentation, deploy the Worker again,
and rerun the real two-page-or-larger smoke test. Do not replace this with
Modal `map()` for the personal-use profile unless parallel GPU containers and
their cost are intentional; the current deployment keeps `max_containers=1`.
Larger batches reduce call/model-load overhead but increase serialized payload,
peak memory and call duration. Keep four as the default until broader fixture
measurements support another value. None of these adjustments should change
MTU detection, OCR, merge, mask, inpaint or rendering algorithms.

## Contract invariants

- Contract version is `saber-native-mtu-page/v3`.
- `extract_page` returns `mtu-extraction/v1` with unique stable region IDs.
- `render_page` requires exactly one string translation for every extracted ID.
- `extract_pages` and `render_pages` accept 1–8 unique page IDs; every page
  still runs the original per-page MTU controller half in isolation.
- Both calls reject credential-shaped fields and enforce the pinned MTU revision.
- Complete `TextBlock.to_dict()` data crosses the pause and is rehydrated before
  MTU completion.
- Pinned MTU stores angled `lines` counter-rotated in `to_dict()`; the adapter
  restores live coordinates with the serialized `angle` and `center` before
  mask refinement. This is a v3 mapping fix, not a new wire field or model.
- Model and SDK imports remain lazy; importing the CLI does not load MTU or Modal.

Offline tests prove the contract boundaries, not broad model quality or cloud
health. A 2026-09-20 ephemeral Modal L4 run executed the v2 single-page runtime on
the public 3065×4096 page: it extracted four stable-ID regions, crossed the
serialization boundary, injected saved translations, rehydrated TextBlocks,
and produced a final image pixel-identical to the same-process native baseline.
It did not call DeepSeek.

On 2026-09-21 the v3 Worker was deployed and one real two-page request used
`extract_pages` once and `render_pages` once on public 3066×4096 and 3065×4096
fixtures. Extraction took 98.195 seconds and returned five plus four regions;
completion took 45.261 seconds. Both pages had zero runtime warnings and both
final images contained actual clean-to-final pixel changes. The smoke test fed
the extracted source strings back as translations, so it verified the batch
wire, warm-runtime reuse and native MTU writeback without calling DeepSeek; it
was not a visible translation result or a translation-language quality
evaluation.

A corrective follow-up reused those saved real extractions and sent nine
explicit Simplified Chinese strings through one real `render_pages` call. It
completed in 200.111 seconds with zero warnings, and visual inspection
confirmed Chinese text in all nine detected regions. Compared with the
source-text render, 436,005 pixels changed on page 1 and 778,491 on page 2.
This proves visible translated-string writeback, but the strings were supplied
explicitly rather than by DeepSeek because no API key was present in the
control environment. Broader fixtures, API translation quality, and a
persistent deployed-app health check remain separate work.
