import json
import subprocess
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

from src.core.ocr_types import OcrResult
from src.core.page_pipeline import PagePipelineOptions, run_page_pipeline
from src.core.pipeline_profiles import register_pipeline_profile, unregister_pipeline_profile
from src.core.stage_backends import register_stage_backend, unregister_stage_backend


BACKEND = "headless_fixture"
PROFILE = "headless_fixture"


class Detector:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, image, **_options):
        self.calls.append("detect")
        mask = np.zeros((image.height, image.width), dtype=np.uint8)
        mask[4:16, 4:16] = 255
        return {
            "coords": [[2, 2, 18, 18]],
            "polygons": [[[2, 2], [18, 2], [18, 18], [2, 18]]],
            "angles": [0],
            "auto_directions": ["v"],
            "textlines_per_bubble": [[]],
            "raw_mask": mask,
        }


class Ocr:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, _image, coords, **_options):
        self.calls.append("ocr")
        return [OcrResult(text="原文", engine="fixture") for _ in coords]


class Color:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, _image, coords, **_options):
        self.calls.append("color")
        return [{"fg_color": [1, 2, 3], "bg_color": [250, 251, 252]} for _ in coords]


class Translator:
    def __init__(self, calls, mismatch=False):
        self.calls, self.mismatch = calls, mismatch

    def execute(self, texts, **_options):
        self.calls.append("translate")
        return [] if self.mismatch else ["译文" for _ in texts]


class Inpainter:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, image, coords, **_options):
        self.calls.append("inpaint")
        self.options = _options
        result = image.copy()
        draw = ImageDraw.Draw(result)
        for coord in coords:
            draw.rectangle(coord, fill="white")
        return result, result.copy()


class Renderer:
    def __init__(self, calls):
        self.calls = calls

    def execute(self, image, states, *, auto_font_size=False):
        self.calls.append("render")
        self.auto_font_size = auto_font_size
        self.states = states
        result = image.copy()
        result.putpixel((10, 10), (0, 0, 0))
        return result


class PagePipelineTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.translator = Translator(self.calls)
        self.inpainter = Inpainter(self.calls)
        self.renderer = Renderer(self.calls)
        implementations = {
            "detect": Detector(self.calls),
            "ocr": Ocr(self.calls),
            "color": Color(self.calls),
            "translate": self.translator,
            "inpaint": self.inpainter,
            "render": self.renderer,
        }
        for stage, implementation in implementations.items():
            register_stage_backend(stage, BACKEND, lambda _local, value=implementation: value)
        register_pipeline_profile(PROFILE, {stage: BACKEND for stage in implementations})

    def tearDown(self):
        unregister_pipeline_profile(PROFILE)
        for stage in ("detect", "ocr", "color", "translate", "inpaint", "render"):
            unregister_stage_backend(stage, BACKEND)

    def test_runs_all_stage_ports_and_returns_real_image_artifacts(self):
        source = Image.new("RGB", (20, 20), "black")
        result = run_page_pipeline(
            source,
            profile=PROFILE,
            options=PagePipelineOptions(auto_font_size=True, inpaint_method="lama_mpe"),
        )

        self.assertEqual(self.calls, ["detect", "ocr", "color", "translate", "inpaint", "render"])
        self.assertEqual(source.getpixel((10, 10)), (0, 0, 0))
        self.assertEqual(result.clean_image.getpixel((10, 10)), (255, 255, 255))
        self.assertEqual(result.final_image.getpixel((10, 10)), (0, 0, 0))
        self.assertEqual(result.bubble_states[0].original_text, "原文")
        self.assertEqual(result.bubble_states[0].translated_text, "译文")
        self.assertEqual(result.bubble_states[0].text_direction, "vertical")
        self.assertEqual(result.bubble_states[0].auto_fg_color, (1, 2, 3))
        self.assertTrue(self.renderer.auto_font_size)
        self.assertEqual(self.inpainter.options["mask_dilate_size"], 10)
        self.assertEqual(self.inpainter.options["mask_box_expand_ratio"], 20)
        document = result.to_document(artifacts={"clean": "clean.png", "rendered": "final.png"})
        self.assertEqual(document["pipelineProfile"], PROFILE)
        self.assertEqual(document["artifacts"]["rendered"], "final.png")
        json.dumps(document)

    def test_rejects_misaligned_translation_before_image_writeback(self):
        self.translator.mismatch = True
        with self.assertRaisesRegex(ValueError, "翻译结果数量"):
            run_page_pipeline(
                Image.new("RGB", (20, 20), "black"),
                profile=PROFILE,
                options=PagePipelineOptions(auto_font_size=False),
            )
        self.assertEqual(self.calls, ["detect", "ocr", "color", "translate"])

    def test_rejects_unsafe_mask_settings_before_running_stages(self):
        with self.assertRaisesRegex(ValueError, "mask_dilate_size"):
            run_page_pipeline(
                Image.new("RGB", (20, 20), "black"),
                profile=PROFILE,
                options=PagePipelineOptions(mask_dilate_size=129),
            )
        self.assertEqual(self.calls, [])

    def test_cli_import_does_not_load_ui_or_model_runtimes(self):
        command = (
            "import sys; import tools.translate_page; "
            "blocked=('flask','torch','modal','manga_translator'); "
            "assert not any(n == b or n.startswith(b + '.') for n in sys.modules for b in blocked)"
        )
        result = subprocess.run([sys.executable, "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
