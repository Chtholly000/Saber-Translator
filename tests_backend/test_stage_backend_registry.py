import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.stage_backends import (  # noqa: E402
    UnsupportedStageBackend,
    create_stage_backend,
    register_stage_backend,
    registered_stage_backends,
    unregister_stage_backend,
)


class StageBackendRegistryTests(unittest.TestCase):
    def test_local_handler_is_preserved_for_its_stage(self) -> None:
        calls = []

        def local_translate(texts, **options):
            calls.append((texts, options))
            return [text.upper() for text in texts]

        backend = create_stage_backend(
            "translate",
            "LOCAL",
            local_handler=local_translate,
        )
        self.assertEqual(backend.name, "local")
        self.assertEqual(backend.execute(["one"], target_language="zh"), ["ONE"])
        self.assertEqual(calls, [(["one"], {"target_language": "zh"})])

    def test_remote_backend_registration_is_scoped_to_one_stage(self) -> None:
        class FixtureBackend:
            name = "fixture_remote"

            def execute(self, value, **_options):
                return f"remote:{value}"

        register_stage_backend(
            "inpaint",
            "fixture-remote",
            lambda _local_handler: FixtureBackend(),
        )
        try:
            backend = create_stage_backend(
                "inpaint",
                "fixture_remote",
                local_handler=lambda value: value,
            )
            self.assertEqual(backend.execute("image"), "remote:image")
            self.assertIn("fixture_remote", registered_stage_backends("inpaint"))
            with self.assertRaises(UnsupportedStageBackend):
                create_stage_backend(
                    "render",
                    "fixture_remote",
                    local_handler=lambda value: value,
                )
        finally:
            unregister_stage_backend("inpaint", "fixture_remote")

    def test_extraction_stages_remain_in_their_dedicated_registry(self) -> None:
        with self.assertRaisesRegex(ValueError, "可用: translate, inpaint, render"):
            create_stage_backend(
                "ocr",
                "local",
                local_handler=lambda value: value,
            )


if __name__ == "__main__":
    unittest.main()
