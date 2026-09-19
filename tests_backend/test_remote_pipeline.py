"""Real adapters/routes with offline transports; never contacts a cloud service."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
import numpy as np
from PIL import Image
from flask import Flask

from src.core.mtu_worker_contract import (
    MTU_WORKER_CONTRACT_VERSION, MtuWorkerContractError,
    encode_worker_png, decode_worker_png,
)
from src.core.extraction_backends import unregister_extraction_backend
from src.core.pipeline_profiles import get_pipeline_profile, unregister_pipeline_profile
from src.core.remote_bootstrap import configure_remote_backends
from src.core.modal_worker_client import ModalWorkerClient
from src.core.stage_backends import unregister_stage_backend
from src.core.stage_backends.deepseek import DeepSeekTranslationBackend
from src.core.stage_backends.mtu_inpaint import build_repair_mask
from workers.mtu.runtime import MtuWorkerRuntime, PinnedMtuEngine


class FixtureEngine:
    def __init__(self):
        self.calls = []

    async def detect(self, image, options):
        self.calls.append(("detect", options))
        return {"regions": [{"coords": [1, 1, 10, 10], "direction": "h", "textlines": []}],
                "text_mask": encode_worker_png(Image.new("L", image.size, 255))}

    async def recognize(self, image, regions, options, *, colors=False):
        self.calls.append(("color" if colors else "ocr", options))
        return {"results": [{"id": r["id"], "text": "original", "engine": "fixture",
                             "fg_color": [10, 20, 30], "bg_color": [255, 255, 255]}
                            for r in reversed(regions)]}

    async def inpaint(self, image, mask, options):
        self.calls.append(("inpaint", options))
        return {"image": encode_worker_png(Image.composite(Image.new("RGB", image.size, "white"), image, mask))}


class OfflineWorker:
    def __init__(self):
        self.engine = FixtureEngine()
        self.runtime = MtuWorkerRuntime(self.engine)
        self.requests = []

    def execute(self, payload):
        self.requests.append(payload)
        return asyncio.run(self.runtime.execute(payload))


def translation_response(request):
    body = json.loads(request.content)
    records = json.loads(body["messages"][-1]["content"])["texts"]
    values = [{"id": r["id"], "text": "译文" + r["id"]} for r in reversed(records)]
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"translations": values})}}]})


class RemotePipelineTests(unittest.TestCase):
    def setUp(self):
        self.worker = OfflineWorker()
        self.config = {"worker": {"app_name": "offline-fixture"},
                       "models": {"detect": {"detector": "ctd", "detection_size": 1024},
                                  "ocr": {"ocr": "48px"},
                                  "inpaint": {"inpainter": "lama_mpe", "inpainting_size": 1024}},
                       "translation": {"model": "fixture", "api_key_env": "SABER_TEST_KEY"}}
        configure_remote_backends(self.config, worker_client=self.worker,
                                  translation_transport=httpx.MockTransport(translation_response))
        path = Path(__file__).resolve().parents[1] / "src/app/api/translation/parallel_routes.py"
        spec = importlib.util.spec_from_file_location("isolated_remote_routes", path)
        self.routes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.routes)
        app = Flask(__name__)
        app.register_blueprint(self.routes.parallel_bp)
        self.client = app.test_client()
        self.image = Image.new("RGB", (20, 20), "black")
        self.encoded = encode_worker_png(self.image)["data"]
        self.keys = patch.dict(os.environ, {"SABER_TEST_KEY": "offline-placeholder"})
        self.keys.start()

    def tearDown(self):
        self.keys.stop()
        unregister_pipeline_profile("modal_mtu_deepseek")
        unregister_extraction_backend("modal_mtu")
        for stage, name in (("translate", "deepseek"), ("inpaint", "modal_mtu"), ("color", "modal_mtu")):
            unregister_stage_backend(stage, name)

    def post(self, stage, **kwargs):
        result = self.client.post("/api/parallel/" + stage, json={
            "pipeline_profile": "modal_mtu_deepseek", "image": self.encoded, **kwargs})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertTrue(result.json["success"], result.json)
        return result.json

    def test_actual_routes_compose_worker_and_api_without_local_gpu(self):
        with patch.object(self.routes, "get_bubble_detection_result_with_auto_directions", side_effect=AssertionError("local GPU")), \
             patch.object(self.routes, "recognize_ocr_results_in_bubbles", side_effect=AssertionError("local GPU")), \
             patch.object(self.routes, "extract_bubble_colors", side_effect=AssertionError("local GPU")), \
             patch.object(self.routes, "inpaint_bubbles", side_effect=AssertionError("local GPU")), \
             patch.object(self.routes, "translate_text_list", side_effect=AssertionError("legacy translation")):
            detection = self.post("detect")
            coords = detection["bubble_coords"]
            ocr = self.post("ocr", bubble_coords=coords, baidu_api_key="must-not-reach-worker",
                            ai_vision_api_key="must-not-reach-worker")
            self.assertEqual(ocr["original_texts"], ["original"])
            colors = self.post("color", bubble_coords=coords)
            self.assertEqual(colors["colors"][0]["autoFgColor"], [10, 20, 30])
            translation = self.post("translate", original_texts=["a", "", "b"], target_language="zh")
            self.assertEqual(translation["translated_texts"], ["译文0", "", "译文2"])
            self.post("inpaint", bubble_coords=coords, method="lama", mask_dilate_size=0)
        self.assertEqual([stage for stage, _ in self.worker.engine.calls], ["detect", "ocr", "color", "inpaint"])
        self.assertEqual(self.worker.engine.calls[0][1], {"detector": "ctd", "detection_size": 1024})
        self.assertEqual(self.worker.engine.calls[1][1], {"ocr": "48px", "source_language": "japanese"})
        self.assertEqual(self.worker.engine.calls[3][1], {"inpainter": "lama_mpe", "inpainting_size": 1024})
        self.assertNotIn("must-not-reach-worker", json.dumps(self.worker.requests))

    def test_profile_discovery_has_no_credentials_and_bootstrap_is_lazy(self):
        result = self.client.get("/api/parallel/profiles").json
        self.assertEqual(self.worker.requests, [])
        self.assertIn("modal_mtu_deepseek", [p["name"] for p in result["profiles"]])
        self.assertNotIn("SABER_TEST_KEY", json.dumps(result))
        self.assertEqual(get_pipeline_profile("modal_mtu_deepseek").backend_for("color"), "modal_mtu")
        local = next(profile for profile in result["profiles"] if profile["name"] == "local_saber")
        self.assertEqual(local["stage_backends"]["color"], "local")

    def test_empty_color_response_keeps_profile_provenance(self):
        result = self.post("color", bubble_coords=[])
        self.assertEqual(result["colors"], [])
        self.assertEqual(result["pipeline_profile"], "modal_mtu_deepseek")
        self.assertEqual(result["execution_backend"], "modal_mtu")

    def test_brush_only_inpaint_does_not_get_skipped(self):
        mask = Image.new("L", self.image.size, 127)
        mask.putpixel((0, 0), 255)
        self.post("inpaint", bubble_coords=[], user_mask=encode_worker_png(mask)["data"], method="lama")
        self.assertEqual(self.worker.engine.calls[0][0], "inpaint")

    def test_mask_user_preservation_wins_after_dilation(self):
        brush = np.full((20, 20), 127, dtype=np.uint8)
        brush[2, 2], brush[19, 19] = 0, 255
        mask = np.array(build_repair_mask(self.image, [[1, 1, 10, 10]], user_mask=brush, mask_dilate_size=2))
        self.assertEqual(mask[2, 2], 0)
        self.assertEqual(mask[19, 19], 255)

    def test_worker_rejects_mismatched_mask_and_undeclared_options(self):
        payload = {"contract_version": MTU_WORKER_CONTRACT_VERSION, "stage": "inpaint",
                   "image": encode_worker_png(self.image), "mask": encode_worker_png(Image.new("L", (1, 1))), "options": {}}
        with self.assertRaises(MtuWorkerContractError):
            self.worker.execute(payload)
        payload.update(stage="detect", options={"api_key": "not-allowed"})
        with self.assertRaises(MtuWorkerContractError):
            self.worker.execute(payload)
        self.assertEqual(self.worker.engine.calls, [])

    def test_adapter_rejects_malformed_worker_geometry_before_it_reaches_the_ui(self):
        class BadGeometryWorker:
            def execute(self, _payload):
                return {"contract_version": MTU_WORKER_CONTRACT_VERSION, "stage": "detect",
                        "regions": [{"coords": [1, 1, 10, 10],
                                     "polygon": [[1, 1], [10, 1]],
                                     "textlines": []}]}

        from src.core.extraction_backends.mtu_modal import ModalMtuExtractionBackend
        with self.assertRaises(MtuWorkerContractError):
            ModalMtuExtractionBackend(BadGeometryWorker()).detect(self.image)

    def test_translation_missing_duplicate_ids_fail_without_partial_results(self):
        for values in ([], [{"id": "0", "text": "a"}, {"id": "0", "text": "b"}], [{"id": "9", "text": "x"}]):
            transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [{"message": {
                "content": json.dumps({"translations": values})}}]}))
            backend = DeepSeekTranslationBackend(model="fixture", api_key_env="SABER_TEST_KEY", transport=transport)
            with self.assertRaises(ValueError):
                backend.execute(["source"], target_language="zh")

    def test_translation_rejects_invalid_input_without_touching_a_transport(self):
        backend = DeepSeekTranslationBackend(
            model="fixture", api_key_env="SABER_TEST_KEY",
            transport=httpx.MockTransport(lambda _request: self.fail("transport must not run")),
        )
        with self.assertRaises(ValueError):
            backend.execute(["valid", 2], target_language="zh")
        with self.assertRaises(ValueError):
            backend.execute(["valid"], target_language="")
        with self.assertRaises(ValueError):
            backend.execute(["valid"], target_language="zh", prompt_content={})

    def test_worker_failure_never_falls_back(self):
        with patch.object(self.worker, "execute", side_effect=RuntimeError("offline failure")):
            result = self.client.post("/api/parallel/detect", json={"image": self.encoded,
                                       "pipeline_profile": "modal_mtu_deepseek"})
        self.assertFalse(result.json["success"])

    def test_modal_client_is_lazy_and_uses_only_the_configured_class(self):
        calls = []

        class FakeWorker:
            def __init__(self):
                self.execute = SimpleNamespace(remote=lambda payload: {"echo": payload})

        class FakeCls:
            @staticmethod
            def from_name(app_name, class_name, **kwargs):
                calls.append((app_name, class_name, kwargs))
                return FakeWorker

        client = ModalWorkerClient("saber-mtu-test", environment_name="staging")
        self.assertEqual(calls, [])
        with patch.dict(sys.modules, {"modal": SimpleNamespace(Cls=FakeCls)}):
            self.assertEqual(client.execute({"stage": "detect"}), {"echo": {"stage": "detect"}})
            client.execute({"stage": "ocr"})
        self.assertEqual(calls, [("saber-mtu-test", "MtuWorker", {"environment_name": "staging"})])


class VendorMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_ocr_reorders_lines_and_preserves_empty_regions(self):
        class Quad:
            def __init__(self, points, text, probability):
                self.pts, self.text, self.prob = points, text, probability

        async def recognize(_engine, _image, lines, _config, *, device):
            if lines[0].pts[0, 0] > 10:
                return []
            for index, line in enumerate(lines):
                line.text, line.prob = str(index), 0.8
            return list(reversed(lines))

        config = SimpleNamespace(Ocr=lambda v: v, OcrConfig=lambda **kw: SimpleNamespace(**kw))
        engine = PinnedMtuEngine(device="cpu", bindings=SimpleNamespace(config=config, ocr=recognize, quad=Quad))
        p1 = [[1, 1], [5, 1], [5, 5], [1, 5]]
        p2 = [[5, 1], [10, 1], [10, 5], [5, 5]]
        regions = [{"id": "first", "coords": [1, 1, 10, 10],
                    "textlines": [{"polygon": p1}, {"polygon": p2}]},
                   {"id": "empty", "coords": [12, 1, 18, 10]}]
        result = await engine.recognize(Image.new("RGB", (20, 20)), regions, {"ocr": "48px"})
        self.assertEqual([r["text"] for r in result["results"]], ["0\n1", ""])
        self.assertFalse(result["results"][1]["confidenceSupported"])

    async def test_detect_maps_rotated_block_without_losing_lines_or_mask(self):
        pts = np.array([[2, 1], [10, 3], [8, 10], [0, 8]])
        block = SimpleNamespace(xyxy=np.array([0, 1, 10, 10]), direction="v", angle=15,
                                min_rect=pts[None, ...], lines=pts[None, ...])
        async def detect(*args, **kwargs):
            return [SimpleNamespace(clip=lambda *_: None)], np.ones((20, 20), dtype=np.uint8), None
        async def merge(*args):
            return [block]
        def detector_config(**options):
            return SimpleNamespace(detector="default", detection_size=1024, text_threshold=.5,
                                   box_threshold=.7, unclip_ratio=2.3, min_box_area_ratio=.0009)
        config = SimpleNamespace(Config=SimpleNamespace, DetectorConfig=detector_config)
        engine = PinnedMtuEngine(device="cpu", bindings=SimpleNamespace(config=config, detect=detect, merge=merge))
        result = await engine.detect(Image.new("RGB", (20, 20)), {})
        self.assertEqual(result["regions"][0]["angle"], 15)
        self.assertEqual(result["regions"][0]["textlines"][0]["polygon"], pts.tolist())
        self.assertEqual(decode_worker_png(result["text_mask"], mode="L").getpixel((0, 0)), 255)


if __name__ == "__main__":
    unittest.main()
