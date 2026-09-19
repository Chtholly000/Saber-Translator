"""Exercise configured plugins through real routes and headless clients, offline."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask
import numpy as np
from PIL import Image

from src.core.ocr_types import OcrResult
from src.core.mtu_worker_contract import encode_worker_png
from src.core.pipeline_plugins import configure_pipeline_plugins
from src.core.pipeline_plugins.loader import STAGES
from src.core.pipeline_profiles import get_pipeline_profile, registered_pipeline_profiles
from src.core.stage_backends import create_stage_backend, registered_stage_backends

ROOT = Path(__file__).resolve().parents[1]
EVENTS = []


def build_fixture(*, stage, invalid=False, fail=False):
    EVENTS.append(("build", stage))

    def execute(*args, **options):
        EVENTS.append(("execute", stage, options))
        if fail:
            raise RuntimeError("credential-must-not-be-returned")
        if invalid:
            return []
        if stage == "detect":
            return {"coords": [[1, 1, 8, 8]], "raw_mask": np.ones((10, 10), dtype=np.uint8)}
        if stage == "ocr":
            return [OcrResult(text="plugin OCR", engine="fixture") for _ in args[1]]
        if stage == "color":
            return [{"fg_color": [1, 2, 3], "bg_color": None} for _ in args[1]]
        if stage == "translate":
            return ["译文" for _ in args[0]]
        if stage == "inpaint":
            return args[0].copy(), args[0].copy()
        if stage == "render":
            return Image.new("RGB", args[0].size, "red")
        raise AssertionError(stage)

    # An OCR-only plugin has execute/close, no detector API at all.
    return SimpleNamespace(execute=execute, close=lambda: EVENTS.append(("close", stage)))


def config_for(stages=STAGES):
    return {"schema_version": 1,
            "plugins": [{"stage": stage, "name": "fixture_" + stage,
                         "factory": "tests_backend.test_pipeline_plugins:build_fixture",
                         "options": {"stage": stage}} for stage in stages],
            "profiles": {"fixture_plugins": {"extends": "local_saber",
                          "stages": {stage: "fixture_" + stage for stage in stages}}}}


class PipelinePluginTests(unittest.TestCase):
    def setUp(self):
        EVENTS.clear()
        spec = importlib.util.spec_from_file_location("isolated_plugin_routes", ROOT / "src/app/api/translation/parallel_routes.py")
        self.routes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.routes)
        app = Flask(__name__)
        app.register_blueprint(self.routes.parallel_bp)
        self.client = app.test_client()
        self.image = Image.new("RGB", (10, 10), "white")
        self.encoded = encode_worker_png(self.image)["data"]

    def install(self, config):
        installation = configure_pipeline_plugins(config)
        self.addCleanup(installation.close)
        return installation

    def backend(self, stage):
        return create_stage_backend(stage, "fixture_" + stage, local_handler=lambda *_: self.fail("local fallback"))

    def post(self, stage, **values):
        response = self.client.post("/api/parallel/" + stage, json={
            "image": self.encoded, "pipeline_profile": "fixture_plugins", **values})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["success"], response.json)
        self.assertEqual(response.json["execution_backend"], "fixture_" + stage)
        return response.json

    def test_all_six_stages_load_through_real_routes_without_local_algorithms(self):
        self.install(config_for())
        with patch.object(self.routes, "get_bubble_detection_result_with_auto_directions", side_effect=AssertionError("local")), \
             patch.object(self.routes, "recognize_ocr_results_in_bubbles", side_effect=AssertionError("local")), \
             patch.object(self.routes, "translate_text_list", side_effect=AssertionError("local")), \
             patch.object(self.routes, "extract_bubble_colors", side_effect=AssertionError("local")), \
             patch.object(self.routes, "inpaint_bubbles", side_effect=AssertionError("local")), \
             patch.object(self.routes, "render_bubbles_unified", side_effect=AssertionError("local")), \
             patch.object(self.routes, "calculate_auto_font_size", side_effect=AssertionError("local sizing")):
            coords = self.post("detect")["bubble_coords"]
            self.assertEqual(self.post("ocr", bubble_coords=coords, baidu_api_key="browser-key")["original_texts"], ["plugin OCR"])
            self.post("color", bubble_coords=coords)
            self.post("translate", original_texts=["text"], api_key="browser-key", custom_base_url="https://unused.invalid",
                      use_textbox_prompt=True, textbox_prompt_content="textbox")
            self.post("inpaint", bubble_coords=coords)
            self.post("render", clean_image=self.encoded,
                      bubble_states=[{"coords": coords[0], "translatedText": "hi"}], autoFontSize=True)
        builds = [event[1] for event in EVENTS if event[0] == "build"]
        self.assertEqual(set(builds), set(STAGES))
        self.assertEqual(len(builds), len(STAGES))
        calls = [event for event in EVENTS if event[0] == "execute"]
        self.assertNotIn("browser-key", repr(calls))
        self.assertNotIn("unused.invalid", repr(calls))
        self.assertTrue(next(event for event in calls if event[1] == "render")[2]["auto_font_size"])

    def test_replace_only_ocr_keeps_every_other_port_and_local_behavior(self):
        self.install(config_for(("ocr",)))
        profile = get_pipeline_profile("fixture_plugins")
        self.assertEqual(profile.backend_for("ocr"), "fixture_ocr")
        for stage in set(STAGES) - {"ocr"}:
            self.assertEqual(profile.backend_for(stage), "local")
        with patch.object(self.routes, "get_bubble_detection_result_with_auto_directions", return_value={"coords": [[1, 1, 8, 8]]}) as detect:
            response = self.client.post("/api/parallel/detect", json={"image": self.encoded, "pipeline_profile": "fixture_plugins"})
            self.assertEqual(response.json["execution_backend"], "local")
            detect.assert_called_once()
        self.post("ocr", bubble_coords=[[1, 1, 8, 8]])
        self.assertNotIn("fixture_ocr", registered_stage_backends("detect"))
        self.assertFalse(hasattr(self.backend("ocr")._instance, "detect"))

    def test_registration_discovery_and_unused_plugin_shutdown_never_import_plugin(self):
        config = config_for(("ocr",))
        config["plugins"][0]["factory"] = "uninstalled_private_package:build"
        with patch("src.core.pipeline_plugins.loader.import_module", side_effect=AssertionError("eager import")):
            installation = self.install(config)
            data = self.client.get("/api/parallel/profiles").json
            backends = self.client.get("/api/parallel/backends").json
            self.assertIn("fixture_ocr", backends["backends"]["ocr"])
            self.assertNotIn("uninstalled_private_package", json.dumps([data, backends]))
            self.assertNotIn("factory", json.dumps([data, backends]))
            installation.close()
        self.assertEqual(EVENTS, [])

    def test_lazy_model_is_reused_across_concurrent_calls_and_closed_once(self):
        installation = self.install(config_for(("ocr",)))
        def run(_):
            return self.backend("ocr").execute(self.image, [[1, 1, 8, 8]])
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(run, range(8)))
        self.assertEqual(EVENTS.count(("build", "ocr")), 1)
        old = self.backend("ocr")
        installation.close()
        installation.close()
        self.assertEqual(EVENTS.count(("close", "ocr")), 1)
        with self.assertRaisesRegex(RuntimeError, "已关闭"):
            old.execute(self.image, [])

    def test_invalid_configuration_never_leaves_partial_registrations(self):
        bad = []
        config = config_for(("ocr",)); config["profiles"]["fixture_plugins"]["stages"]["detect"] = "absent"; bad.append(config)
        config = config_for(("ocr",)); config["plugins"].append(deepcopy(config["plugins"][0])); bad.append(config)
        config = config_for(("ocr",)); config["plugins"][0]["factory"] = "./arbitrary.py"; bad.append(config)
        config = config_for(("ocr",)); config["profiles"]["fixture_plugins"]["extends"] = "fixture_plugins"; bad.append(config)
        config = config_for(("ocr",)); config["plugins"][0]["stage"] = "unknown"; bad.append(config)
        config = config_for(("ocr",)); config["schema_version"] = 2; bad.append(config)
        config = config_for(("ocr",)); config["plugins"][0]["name"] = "local"; bad.append(config)
        for config in bad:
            with self.subTest(config=config), self.assertRaises(ValueError):
                configure_pipeline_plugins(config)
            self.assertNotIn("fixture_ocr", registered_stage_backends("ocr"))
            self.assertNotIn("fixture_plugins", registered_pipeline_profiles())
        self.assertEqual(EVENTS, [])

    def test_invalid_output_rejected_for_every_stage(self):
        config = config_for()
        for plugin in config["plugins"]:
            plugin["options"]["invalid"] = True
        self.install(config)
        for stage in STAGES:
            args = (["text"],) if stage == "translate" else (self.image, [[1, 1, 8, 8]])
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "契约"):
                self.backend(stage).execute(*args)

    def test_plugin_failure_is_redacted_and_never_falls_back(self):
        config = config_for(("ocr",))
        config["plugins"][0]["options"]["fail"] = True
        self.install(config)
        response = self.client.post("/api/parallel/ocr", json={"image": self.encoded,
            "pipeline_profile": "fixture_plugins", "bubble_coords": [[1, 1, 8, 8]]})
        self.assertFalse(response.json["success"])
        self.assertNotIn("credential-must-not-be-returned", response.get_data(as_text=True))

    def test_profile_inheritance_can_replace_ocr_independent_of_definition_order(self):
        config = config_for()
        config["profiles"] = {"derived": {"extends": "fixture_plugins", "stages": {"ocr": "local"}}, **config["profiles"]}
        self.install(config)
        base, derived = get_pipeline_profile("fixture_plugins"), get_pipeline_profile("derived")
        self.assertEqual(derived.backend_for("ocr"), "local")
        self.assertEqual(base.backend_for("ocr"), "fixture_ocr")
        for stage in set(STAGES) - {"ocr"}:
            self.assertEqual(base.backend_for(stage), derived.backend_for(stage))

    def test_headless_extraction_and_typesetting_use_same_plugin_ports(self):
        from tools.extract_text import extract_text
        from tools.typeset import typeset
        self.install(config_for())
        document = extract_text(self.image, profile="fixture_plugins")
        self.assertEqual(document["bubble_states"][0]["originalText"], "plugin OCR")
        result = typeset(self.image, document, profile="fixture_plugins")
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual([e[1] for e in EVENTS if e[0] == "execute"], ["detect", "ocr", "render"])

    def test_checked_in_examples_validate_without_gpu_or_sdk_imports(self):
        for path in ("provided-text.example.json", "mtu.example.json"):
            with (ROOT / "pipeline_plugins" / path).open() as handle:
                self.install(json.load(handle))
        result = subprocess.run([sys.executable, "-c", """
import json, sys
from src.core.pipeline_plugins import configure_pipeline_plugins
with open('pipeline_plugins/mtu.example.json') as handle:
    installation = configure_pipeline_plugins(json.load(handle))
assert not any(name in sys.modules for name in ('torch', 'modal', 'manga_translator'))
installation.close()
"""], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_supplied_text_example_is_an_executable_ocr_only_plugin(self):
        with (ROOT / "pipeline_plugins/provided-text.example.json").open() as handle:
            self.install(json.load(handle))
        response = self.client.post("/api/parallel/ocr", json={
            "image": self.encoded, "pipeline_profile": "custom_ocr",
            "bubble_coords": [[1, 1, 8, 8]],
        })
        self.assertTrue(response.json["success"], response.json)
        self.assertEqual(response.json["original_texts"], ["示例原文"])
        self.assertEqual(response.json["execution_backend"], "provided_text")

    def test_mtu_plugin_factories_dispatch_both_ocr_models_and_normalize_all_gpu_stages(self):
        from tests_backend.test_remote_pipeline import OfflineWorker
        worker = OfflineWorker()
        with (ROOT / "pipeline_plugins/mtu.example.json").open() as handle:
            self.install(json.load(handle))
        with patch("src.core.pipeline_plugins.factories._client", return_value=worker):
            for profile in ("modular_mtu", "modular_mtu_mocr"):
                for stage in ("detect", "ocr", "color", "inpaint"):
                    name = get_pipeline_profile(profile).backend_for(stage)
                    backend = create_stage_backend(stage, name, local_handler=lambda *_: self.fail("local"))
                    args = (self.image,) if stage == "detect" else (self.image, [[1, 1, 8, 8]])
                    backend.execute(*args)
        ocr_calls = [options for stage, options in worker.engine.calls if stage == "ocr"]
        self.assertEqual([options["ocr"] for options in ocr_calls], ["48px", "mocr"])
        self.assertNotIn("deepseek", [event[1] for event in EVENTS])


if __name__ == "__main__":
    unittest.main()
