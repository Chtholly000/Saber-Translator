import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

from src.core.mtu_worker_contract import MtuWorkerContractError, encode_worker_png
from src.core.native_mtu_page_contract import (
    NATIVE_MTU_PAGE_CONTRACT_VERSION,
    PINNED_MTU_REVISION,
    build_native_mtu_extract_batch_request,
    build_native_mtu_extract_request,
    build_native_mtu_render_request,
)
from src.core.native_page_bootstrap import configure_native_mtu_page_engine
from src.core.page_engines import create_page_engine, unregister_page_engine
from src.core.page_engines.base import PageEngineResult


def _region():
    return {
        "id": "region-0000",
        "text": "原文",
        "native": {
            "lines": [[[1, 1], [3, 1], [3, 3], [1, 3]]],
            "texts": ["原文"],
            "text": "原文",
            "translation": "",
            "font_size": 22,
        },
    }


class _Translator:
    name = "fixture_translator"

    def __init__(self):
        self.calls = []

    def execute(self, texts, **options):
        self.calls.append((list(texts), dict(options)))
        return [f"译文-{index}" for index, _ in enumerate(texts)]


class _WorkerClient:
    def __init__(self):
        self.calls = []

    def execute(self, payload):
        self.calls.append(payload)
        common = {
            "contract_version": NATIVE_MTU_PAGE_CONTRACT_VERSION,
            "operation": payload["operation"],
            "mtu_revision": PINNED_MTU_REVISION,
        }
        if payload["operation"] == "extract_pages":
            return {
                **common,
                "pages": [self._extract_response(page) for page in payload["pages"]],
            }
        if payload["operation"] == "render_pages":
            self.render_translations_by_page = {
                page["id"]: dict(page["translations"])
                for page in payload["pages"]
            }
            return {
                **common,
                "pages": [self._render_response(page) for page in payload["pages"]],
            }
        size = (payload["image"]["width"], payload["image"]["height"])
        if payload["operation"] == "extract_page":
            return {
                **common,
                **self._extract_response({"id": "single", "image": payload["image"]}, include_id=False),
            }
        self.render_translations = dict(payload["translations"])
        return {
            **common,
            **self._render_response({
                "id": "single",
                "image": payload["image"],
                "translations": payload["translations"],
            }, include_id=False),
        }

    @staticmethod
    def _extract_response(page, *, include_id=True):
        size = (page["image"]["width"], page["image"]["height"])
        result = {
            "working_image": encode_worker_png(Image.new("RGB", size, "white")),
            "raw_mask": encode_worker_png(Image.new("L", size, 255)),
            "extraction_document": {
                "schema": "mtu-extraction/v1",
                "original_width": size[0],
                "original_height": size[1],
                "regions": [_region()],
            },
            "warnings": [],
        }
        return {"id": page["id"], **result} if include_id else result

    @staticmethod
    def _render_response(page, *, include_id=True):
        size = (page["image"]["width"], page["image"]["height"])
        rendered_region = _region()
        rendered_region["native"]["translation"] = page["translations"][
            "region-0000"
        ]
        result = {
            "clean_image": encode_worker_png(Image.new("RGB", size, "white")),
            "final_image": encode_worker_png(Image.new("RGB", size, "black")),
            "repair_mask": encode_worker_png(Image.new("L", size, 255)),
            "native_document": {
                "schema": "mtu-rendered/v1",
                "original_width": size[0],
                "original_height": size[1],
                "regions": [rendered_region],
            },
            "warnings": [],
        }
        return {"id": page["id"], **result} if include_id else result


class NativeMtuPageEngineTests(unittest.TestCase):
    def tearDown(self):
        unregister_page_engine("mtu_native")

    def test_extract_translate_render_are_separate_and_keep_native_data(self):
        client = _WorkerClient()
        translator = _Translator()
        configure_native_mtu_page_engine({
            "worker": {"app_name": "fixture", "class_name": "Fixture"},
            "page": {
                "ocr": {"ocr": "48px"},
                "inpainter": {"inpainter": "lama_mpe"},
            },
            "translation": {
                "backend": "fixture",
                "target_language": "CHS",
            },
        }, worker_client=client, translation_backend=translator)
        self.assertEqual(client.calls, [])

        result = create_page_engine("mtu_native").execute(
            Image.new("RGB", (8, 6), "white")
        )

        self.assertEqual(
            [call["operation"] for call in client.calls],
            ["extract_page", "render_page"],
        )
        self.assertEqual(translator.calls[0][0], ["原文"])
        self.assertEqual(
            translator.calls[0][1]["target_language"],
            "CHS",
        )
        self.assertEqual(client.render_translations, {"region-0000": "译文-0"})
        self.assertEqual(
            result.native_document["regions"][0]["native"]["translation"],
            "译文-0",
        )
        self.assertEqual(result.metadata["translationBackend"], "fixture_translator")
        self.assertNotIn("bubble_states", result.to_document())
        self.assertNotIn("api_key", str(client.calls).lower())

    def test_multiple_pages_use_bounded_gpu_calls_and_one_translation_call(self):
        client = _WorkerClient()
        translator = _Translator()
        configure_native_mtu_page_engine({
            "worker": {"app_name": "fixture", "class_name": "Fixture"},
            "page": {
                "ocr": {"ocr": "48px"},
                "inpainter": {"inpainter": "lama_mpe"},
            },
            "translation": {
                "backend": "fixture",
                "target_language": "CHS",
            },
        }, worker_client=client, translation_backend=translator)

        results = create_page_engine("mtu_native").execute_batch([
            Image.new("RGB", (8, 6), "white"),
            Image.new("RGB", (6, 4), "white"),
        ], gpu_batch_size=4)

        self.assertEqual(
            [call["operation"] for call in client.calls],
            ["extract_pages", "render_pages"],
        )
        self.assertEqual(len(translator.calls), 1)
        self.assertEqual(translator.calls[0][0], ["原文", "原文"])
        self.assertEqual(len(results), 2)
        self.assertEqual(
            client.render_translations_by_page,
            {
                "page-000000": {"region-0000": "译文-0"},
                "page-000001": {"region-0000": "译文-1"},
            },
        )
        self.assertEqual(results[0].metadata["translationBatchPageCount"], 2)
        self.assertEqual(
            results[1].native_document["regions"][0]["native"]["translation"],
            "译文-1",
        )

    def test_contract_rejects_credentials_unknown_modules_and_missing_ids(self):
        image = Image.new("RGB", (4, 4), "white")
        with self.assertRaises(MtuWorkerContractError):
            build_native_mtu_extract_request(
                image,
                {"ocr": {"api_key": "must-not-cross-wire"}},
            )
        with self.assertRaises(MtuWorkerContractError):
            build_native_mtu_extract_request(image, {"invented_stage": {}})
        with self.assertRaises(MtuWorkerContractError):
            build_native_mtu_render_request(
                image,
                Image.new("L", image.size),
                {
                    "schema": "mtu-extraction/v1",
                    "original_width": 4,
                    "original_height": 4,
                    "regions": [_region()],
                },
                {},
                {},
            )
        with self.assertRaises(MtuWorkerContractError):
            build_native_mtu_extract_batch_request(
                [(f"page-{index}", image) for index in range(9)],
                {},
            )

    def test_batch_size_bounds_gpu_calls_without_splitting_translation(self):
        client = _WorkerClient()
        translator = _Translator()
        configure_native_mtu_page_engine({
            "worker": {"app_name": "fixture", "class_name": "Fixture"},
            "page": {},
            "translation": {
                "backend": "fixture",
                "target_language": "CHS",
            },
        }, worker_client=client, translation_backend=translator)

        results = create_page_engine("mtu_native").execute_batch(
            [Image.new("RGB", (4, 4)) for _ in range(5)],
            gpu_batch_size=2,
        )

        self.assertEqual(
            [call["operation"] for call in client.calls],
            ["extract_pages"] * 3 + ["render_pages"] * 3,
        )
        self.assertEqual(len(translator.calls), 1)
        self.assertEqual(len(translator.calls[0][0]), 5)
        self.assertEqual(len(results), 5)

    def test_agent_cli_import_is_lazy(self):
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import tools.translate_page_native; "
                "assert 'modal' not in sys.modules; "
                "assert 'manga_translator' not in sys.modules",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_agent_cli_atomically_writes_multi_page_batch(self):
        from tools import translate_page_native

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [root / "one.png", root / "two.png"]
            for path in inputs:
                Image.new("RGB", (4, 3), "white").save(path)
            config = root / "config.json"
            config.write_text("{}", encoding="utf-8")
            output = root / "result"
            engine = mock.Mock()
            engine.execute_batch.return_value = [
                PageEngineResult(
                    engine="mtu_native",
                    clean_image=Image.new("RGB", (4, 3), "white"),
                    final_image=Image.new("RGB", (4, 3), "black"),
                    repair_mask=Image.new("L", (4, 3), 255),
                    native_document={"regions": []},
                    metadata={"mtuRevision": PINNED_MTU_REVISION, "regionCount": 0},
                )
                for _ in inputs
            ]
            argv = [
                "translate_page_native",
                "--image", str(inputs[0]),
                "--image", str(inputs[1]),
                "--output-dir", str(output),
                "--config", str(config),
                "--gpu-batch-size", "2",
            ]
            with mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(translate_page_native, "configure_native_mtu_page_engine"), \
                    mock.patch.object(translate_page_native, "create_page_engine", return_value=engine), \
                    mock.patch("builtins.print"):
                translate_page_native.main()

            engine.execute_batch.assert_called_once()
            self.assertTrue((output / "batch.json").is_file())
            self.assertTrue((output / "page-0001" / "final.png").is_file())
            document = json.loads((output / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(document["gpuBatchSize"], 2)
            self.assertEqual([page["sourceName"] for page in document["pages"]], [
                "one.png", "two.png",
            ])


if __name__ == "__main__":
    unittest.main()
