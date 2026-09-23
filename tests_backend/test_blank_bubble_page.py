import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

from src.core.blank_bubble_contract import (
    BLANK_BUBBLE_CONTRACT_VERSION,
    build_bubble_detect_request,
    normalize_bubble_detect_response,
)
from src.core.blank_bubble_page import (
    HighContrastContourSlotDetector,
    HybridBubbleSlotDetector,
    ModalMangaLensSlotDetector,
    make_slot_document,
    prepare_text_layout,
    render_supplied_text,
    validate_slot_document,
)
from src.core.mtu_worker_contract import MtuWorkerContractError
from src.core.native_mtu_page_contract import PINNED_MTU_REVISION
from workers.mtu_native.runtime import MtuNativeWorkerRuntime


class _FakeClient:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return {
            "contract_version": BLANK_BUBBLE_CONTRACT_VERSION,
            "operation": "detect_bubbles",
            "mtu_revision": PINNED_MTU_REVISION,
            "image_width": 400,
            "image_height": 240,
            "slots": [
                {"coords": [220, 30, 370, 140], "confidence": 0.93},
                {"coords": [25, 32, 175, 142], "confidence": 0.89},
            ],
        }


class _FakeModelDetector:
    def __init__(self):
        self.calls = []

    def detect(self, image, options):
        self.calls.append((image.size, options))
        return [{"coords": [4, 5, 24, 25], "confidence": 0.81}]


class BlankBubblePageTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (400, 240), "white")
        self.source_bytes = b"fixture image bytes"
        self.client = _FakeClient()
        self.detector = ModalMangaLensSlotDetector(
            {"app_name": "fixture", "class_name": "MtuNativeWorker"},
            client=self.client,
        )

    def test_detect_and_map_supplied_text_without_ocr_or_translation(self):
        document = make_slot_document(self.image, self.source_bytes, self.detector)
        slots = validate_slot_document(document, self.image, self.source_bytes)
        self.assertEqual([slot["id"] for slot in slots], ["slot-0001", "slot-0002"])
        self.assertGreater(slots[0]["coords"][0], slots[1]["coords"][0])
        self.assertEqual(self.client.requests[0]["operation"], "detect_bubbles")
        self.assertEqual(self.client.requests[0]["options"]["image_size"], 1600)
        self.assertNotIn("api_key", str(self.client.requests).lower())

        layout = prepare_text_layout(
            slots, {"slot-0001": "你好", "slot-0002": "世界"}, font_size=22
        )
        self.assertEqual(
            [(item["bubbleId"], item["translatedText"]) for item in layout["bubble_states"]],
            [("slot-0001", "你好"), ("slot-0002", "世界")],
        )
        self.assertGreater(layout["bubble_states"][0]["position"]["y"], 0)
        rendered = render_supplied_text(self.image, layout)
        self.assertEqual(rendered.size, self.image.size)
        self.assertTrue(np.any(np.asarray(rendered) != np.asarray(self.image)))
        self.assertEqual(self.image.getpixel((300, 80)), (255, 255, 255))

    def test_wrong_text_count_or_ids_fail_before_render(self):
        slots = make_slot_document(self.image, self.source_bytes, self.detector)["slots"]
        with self.assertRaisesRegex(ValueError, "数量"):
            prepare_text_layout(slots, ["only one"])
        with self.assertRaisesRegex(ValueError, "ID"):
            prepare_text_layout(slots, {"wrong": "text"})
        with self.assertRaisesRegex(ValueError, "不匹配"):
            validate_slot_document({
                **make_slot_document(self.image, self.source_bytes, self.detector),
                "image_sha256": "0" * 64,
            }, self.image, self.source_bytes)
        document = make_slot_document(self.image, self.source_bytes, self.detector)
        document["slots"][0]["confidence"] = float("nan")
        with self.assertRaisesRegex(ValueError, "置信度"):
            validate_slot_document(document, self.image, self.source_bytes)

    def test_wire_response_rejects_bad_region_and_revision(self):
        response = self.client.execute(build_bubble_detect_request(self.image))
        bad = {**response, "mtu_revision": "other"}
        with self.assertRaises(MtuWorkerContractError):
            normalize_bubble_detect_response(bad, image_size=self.image.size)
        bad = {**response, "slots": [{"coords": [0, 0, 500, 20], "confidence": 0.9}]}
        with self.assertRaises(MtuWorkerContractError):
            normalize_bubble_detect_response(bad, image_size=self.image.size)
        with self.assertRaises(MtuWorkerContractError):
            build_bubble_detect_request(self.image, {"api_key": "not-allowed"})
        bad = {**response, "slots": [{"coords": [1.1, 1, 1.4, 20], "confidence": 0.9}]}
        with self.assertRaises(MtuWorkerContractError):
            normalize_bubble_detect_response(bad, image_size=self.image.size)

    def test_worker_dispatches_only_bubble_model_for_bubble_operation(self):
        model = _FakeModelDetector()
        worker = MtuNativeWorkerRuntime(engine=object(), bubble_detector=model)
        response = asyncio.run(worker.execute(build_bubble_detect_request(self.image)))
        self.assertEqual(response["slots"][0]["coords"], [4, 5, 24, 25])
        self.assertEqual(model.calls[0][0], self.image.size)
        self.assertEqual(response["mtu_revision"], PINNED_MTU_REVISION)

    def test_cli_can_reuse_saved_slots_and_publish_real_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "blank.png"
            image = Image.new("RGB", (400, 240), "white")
            draw = ImageDraw.Draw(image)
            draw.ellipse((220, 30, 370, 140), outline="black", width=4)
            draw.ellipse((25, 32, 175, 142), outline="black", width=4)
            image.save(image_path)
            raw = image_path.read_bytes()
            slots = make_slot_document(image, raw, self.detector)
            slot_path = root / "slots.json"
            slot_path.write_text(json.dumps(slots), encoding="utf-8")
            text_path = root / "texts.json"
            text_path.write_text(json.dumps(["你好", "世界"]), encoding="utf-8")
            output = root / "result"
            process = subprocess.run([
                sys.executable, "-m", "tools.letter_blank_page",
                "--image", str(image_path),
                "--slots", str(slot_path),
                "--texts", str(text_path),
                "--output-dir", str(output),
                "--font-size", "22",
            ], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue((output / "final.png").is_file())
            self.assertTrue((output / "slots-preview.png").is_file())
            with Image.open(output / "final.png") as final:
                self.assertTrue(np.any(np.asarray(final) != np.asarray(image)))
            self.assertEqual(
                [item["bubbleId"] for item in json.loads((output / "layout.json").read_text())["bubble_states"]],
                ["slot-0001", "slot-0002"],
            )

    def test_cli_can_select_subset_without_repeating_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "blank.png"
            self.image.save(image_path)
            slots = make_slot_document(self.image, image_path.read_bytes(), self.detector)
            slot_path = root / "slots.json"
            slot_path.write_text(json.dumps(slots), encoding="utf-8")
            text_path = root / "texts.json"
            text_path.write_text(json.dumps({"slot-0002": "指定框"}), encoding="utf-8")
            output = root / "result"
            process = subprocess.run([
                sys.executable, "-m", "tools.letter_blank_page",
                "--image", str(image_path),
                "--slots", str(slot_path),
                "--select-slot", "slot-0002",
                "--texts", str(text_path),
                "--output-dir", str(output),
                "--font-size", "22",
            ], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout)["selected_count"], 1)
            self.assertEqual(
                len(json.loads((output / "layout.json").read_text())["bubble_states"]), 1
            )

    def test_contour_detector_finds_two_outlined_empty_bubbles_without_gpu(self):
        image = Image.new("RGB", (400, 240), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((225, 25, 365, 135), outline="black", width=6)
        draw.ellipse((35, 40, 175, 150), outline="black", width=6)
        regions = HighContrastContourSlotDetector().detect(image)
        self.assertEqual(len(regions), 2)
        self.assertGreater(regions[0]["confidence"], 0.65)
        merged = HybridBubbleSlotDetector(
            type("Detector", (), {"detect": lambda self, _image: [regions[0]]})(),
            type("Detector", (), {"detect": lambda self, _image: regions})(),
        ).detect(image)
        self.assertEqual(len(merged), 2)


if __name__ == "__main__":
    unittest.main()
