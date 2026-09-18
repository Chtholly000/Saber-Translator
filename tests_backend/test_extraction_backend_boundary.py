import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.extraction_backends import (  # noqa: E402
    UnsupportedExtractionBackend,
    create_extraction_backend,
    register_extraction_backend,
    registered_extraction_backends,
    unregister_extraction_backend,
)


class ExtractionBackendBoundaryTests(unittest.TestCase):
    def test_local_backend_preserves_existing_function_calls(self) -> None:
        calls = []

        def detect(image, **options):
            calls.append(("detect", image, options))
            return {"coords": [[1, 2, 3, 4]]}

        def ocr(image, bubble_coords, **options):
            calls.append(("ocr", image, bubble_coords, options))
            return ["text"]

        backend = create_extraction_backend(
            "LOCAL",
            local_detect=detect,
            local_ocr=ocr,
        )

        self.assertEqual(backend.name, "local")
        self.assertEqual(backend.detect("image", detector_type="default")["coords"], [[1, 2, 3, 4]])
        self.assertEqual(backend.ocr("image", [[1, 2, 3, 4]], ocr_engine="manga_ocr"), ["text"])
        self.assertEqual(calls[0], ("detect", "image", {"detector_type": "default"}))
        self.assertEqual(
            calls[1],
            ("ocr", "image", [[1, 2, 3, 4]], {"ocr_engine": "manga_ocr"}),
        )

    def test_unknown_backend_fails_before_running_local_models(self) -> None:
        with self.assertRaises(UnsupportedExtractionBackend):
            create_extraction_backend(
                "modal",
                local_detect=lambda *_args, **_kwargs: {},
                local_ocr=lambda *_args, **_kwargs: [],
            )

    def test_remote_adapter_can_be_registered_without_changing_routes(self) -> None:
        class FixtureBackend:
            name = "fixture_remote"

            def detect(self, image, **options):
                return {"coords": [], "worker": image}

            def ocr(self, image, bubble_coords, **options):
                return [image, bubble_coords]

        register_extraction_backend(
            "fixture-remote",
            lambda _local_functions: FixtureBackend(),
        )
        try:
            backend = create_extraction_backend(
                "fixture_remote",
                local_detect=lambda *_args, **_kwargs: {},
                local_ocr=lambda *_args, **_kwargs: [],
            )
            self.assertEqual(backend.detect("remote-image")["worker"], "remote-image")
            self.assertIn("fixture_remote", registered_extraction_backends())
        finally:
            unregister_extraction_backend("fixture_remote")


if __name__ == "__main__":
    unittest.main()
