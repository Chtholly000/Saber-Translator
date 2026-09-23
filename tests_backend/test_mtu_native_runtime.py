import asyncio
from types import SimpleNamespace
import unittest

import numpy as np
from PIL import Image

from src.core.mtu_worker_contract import MtuWorkerContractError, decode_worker_png
from src.core.native_mtu_page_contract import (
    build_native_mtu_extract_batch_request,
    build_native_mtu_extract_request,
    build_native_mtu_render_batch_request,
    build_native_mtu_render_request,
    normalize_native_mtu_extract_batch_response,
    normalize_native_mtu_extract_response,
)
from workers.mtu_native.runtime import MtuNativeWorkerRuntime, NativeMtuControllerAdapter


class _FakeConfig:
    payloads = []

    def __init__(self, **payload):
        type(self).payloads.append(payload)


class _FakeTextBlock:
    def __init__(
        self,
        lines,
        texts,
        translation="",
        translation_raw="",
        font_size=22,
        **values,
    ):
        self.lines = np.asarray(lines)
        self.texts = list(texts)
        self.text = self.texts[0]
        self.translation = translation
        self.translation_raw = translation_raw
        self.font_size = font_size
        self.values = values

    def to_dict(self):
        return {
            "lines": self.lines.tolist(),
            "texts": list(self.texts),
            "text": self.text,
            "translation": self.translation,
            "translation_raw": self.translation_raw,
            "font_size": np.int64(self.font_size),
            "fg_colors": [0, 0, 0],
            "bg_colors": [255, 255, 255],
            "stroke_width": 0.2,
        }


class _FakeMangaTranslator:
    instances = []

    def __init__(self, params):
        self.params = params
        self.extract_calls = 0
        self.complete_calls = 0
        self.render_calls = 0
        self._detector_cleanup_task = None
        type(self).instances.append(self)

    async def _translate_until_translation(self, image, config):
        self.extract_calls += 1
        return SimpleNamespace(
            img_rgb=np.array(image, dtype=np.uint8),
            mask_raw=np.full((image.height, image.width), 120, dtype=np.uint8),
            text_regions=[_FakeTextBlock(
                lines=[[[1, 1], [3, 1], [3, 3], [1, 3]]],
                texts=["原文"],
            )],
        )

    async def _complete_translation_pipeline(self, ctx, config):
        self.complete_calls += 1
        ctx.mask = np.full(ctx.img_rgb.shape[:2], 255, dtype=np.uint8)
        ctx.img_inpainted = np.full_like(ctx.img_rgb, 180)
        rendered = await self._run_text_rendering(config, ctx)
        ctx.result = Image.fromarray(rendered)
        return ctx

    async def _run_text_rendering(self, config, ctx, *args, **kwargs):
        self.render_calls += 1
        return np.full_like(ctx.img_inpainted, 40)


class NativeMtuRuntimeTests(unittest.TestCase):
    def setUp(self):
        _FakeConfig.payloads = []
        _FakeMangaTranslator.instances = []
        bindings = SimpleNamespace(
            Config=_FakeConfig,
            MangaTranslator=_FakeMangaTranslator,
            Context=lambda **values: SimpleNamespace(**values),
            TextBlock=_FakeTextBlock,
        )
        self.runtime = MtuNativeWorkerRuntime(
            engine=NativeMtuControllerAdapter(bindings=bindings)
        )

    def test_delegates_both_halves_to_original_controller(self):
        image = Image.new("RGB", (7, 5), "white")
        extract_request = build_native_mtu_extract_request(
            image,
            {
                "ocr": {"ocr": "48px"},
                "translator": {"target_lang": "CHS"},
            },
        )
        extract_response = asyncio.run(self.runtime.execute(extract_request))
        extraction = normalize_native_mtu_extract_response(
            extract_response,
            image_size=image.size,
        )

        self.assertEqual(_FakeMangaTranslator.instances[0].extract_calls, 1)
        region = extraction["extraction_document"]["regions"][0]
        self.assertEqual(region["id"], "region-0000")
        self.assertEqual(region["text"], "原文")
        self.assertEqual(
            extraction["raw_mask"].getpixel((0, 0)),
            120,
        )

        render_request = build_native_mtu_render_request(
            extraction["working_image"],
            extraction["raw_mask"],
            extraction["extraction_document"],
            {"region-0000": "译文"},
            {
                "translator": {"target_lang": "CHS"},
                "inpainter": {"inpainter": "lama_mpe"},
                "controller": {"mask_dilation_offset": 20},
            },
        )
        render_response = asyncio.run(self.runtime.execute(render_request))

        controller = _FakeMangaTranslator.instances[1]
        self.assertEqual(controller.complete_calls, 1)
        self.assertEqual(controller.render_calls, 1)
        self.assertEqual(
            _FakeConfig.payloads[1]["mask_dilation_offset"],
            20,
        )
        self.assertEqual(
            render_response["native_document"]["regions"][0]["native"][
                "translation"
            ],
            "译文",
        )
        self.assertEqual(
            decode_worker_png(render_response["clean_image"]).getpixel((0, 0)),
            (180, 180, 180),
        )
        self.assertEqual(
            decode_worker_png(render_response["final_image"]).getpixel((0, 0)),
            (40, 40, 40),
        )

    def test_raw_worker_request_cannot_carry_secret(self):
        request = build_native_mtu_extract_request(Image.new("RGB", (2, 2)), {})
        request["options"] = {"ocr": {"secret": "no"}}
        with self.assertRaises(MtuWorkerContractError):
            asyncio.run(self.runtime.execute(request))

    def test_batch_invocation_keeps_pages_separate_inside_one_worker_call(self):
        images = [
            ("page-a", Image.new("RGB", (7, 5), "white")),
            ("page-b", Image.new("RGB", (5, 3), "black")),
        ]
        extract_request = build_native_mtu_extract_batch_request(
            images,
            {"ocr": {"ocr": "48px"}},
        )
        extract_response = asyncio.run(self.runtime.execute(extract_request))
        extractions = normalize_native_mtu_extract_batch_response(
            extract_response,
            page_sizes={page_id: image.size for page_id, image in images},
        )

        self.assertEqual(extract_response["operation"], "extract_pages")
        self.assertEqual([item["page_id"] for item in extractions], ["page-a", "page-b"])
        self.assertEqual(len(_FakeMangaTranslator.instances), 2)

        render_request = build_native_mtu_render_batch_request([
            {
                "id": extraction["page_id"],
                "working_image": extraction["working_image"],
                "raw_mask": extraction["raw_mask"],
                "extraction_document": extraction["extraction_document"],
                "translations": {"region-0000": f"译文-{index}"},
            }
            for index, extraction in enumerate(extractions)
        ], {"inpainter": {"inpainter": "lama_mpe"}})
        render_response = asyncio.run(self.runtime.execute(render_request))

        self.assertEqual(render_response["operation"], "render_pages")
        self.assertEqual(
            [page["id"] for page in render_response["pages"]],
            ["page-a", "page-b"],
        )
        self.assertEqual(
            render_response["pages"][1]["native_document"]["regions"][0]["native"]["translation"],
            "译文-1",
        )
        self.assertEqual(len(_FakeMangaTranslator.instances), 4)

    def test_render_rejects_missing_translation_id(self):
        image = Image.new("RGB", (2, 2))
        document = {
            "schema": "mtu-extraction/v1",
            "original_width": 2,
            "original_height": 2,
            "regions": [{
                "id": "region-0000",
                "text": "x",
                "native": {
                    "lines": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
                    "texts": ["x"],
                },
            }],
        }
        with self.assertRaises(MtuWorkerContractError):
            build_native_mtu_render_request(
                image,
                Image.new("L", image.size),
                document,
                {},
                {},
            )


if __name__ == "__main__":
    unittest.main()
