import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline_profiles import (  # noqa: E402
    PIPELINE_STAGES,
    UnsupportedPipelineProfile,
    get_pipeline_profile,
    register_pipeline_profile,
    registered_pipeline_profiles,
    resolve_stage_backend,
    resolve_stage_backend_request,
    unregister_pipeline_profile,
)


class PipelineProfileTests(unittest.TestCase):
    def test_default_profile_is_complete_and_local(self) -> None:
        profile = get_pipeline_profile()

        self.assertEqual(profile.name, "local_saber")
        self.assertEqual(set(profile.stage_backends), set(PIPELINE_STAGES))
        self.assertEqual(
            {profile.backend_for(stage) for stage in PIPELINE_STAGES},
            {"local"},
        )
        self.assertEqual(registered_pipeline_profiles(), ("local_saber",))
        with self.assertRaises(TypeError):
            profile.stage_backends["detect"] = "fixture_remote"

    def test_stage_override_is_explicit_and_does_not_mutate_profile(self) -> None:
        profile, backend = resolve_stage_backend(
            "LOCAL-SABER",
            "detect",
            backend_override="fixture-remote",
        )

        self.assertEqual(profile.name, "local_saber")
        self.assertEqual(backend, "fixture_remote")
        self.assertEqual(profile.backend_for("detect"), "local")

    def test_unknown_profile_and_stage_fail_explicitly(self) -> None:
        with self.assertRaises(UnsupportedPipelineProfile):
            get_pipeline_profile("modal_mtu")
        with self.assertRaises(UnsupportedPipelineProfile):
            resolve_stage_backend("local_saber", "layout")

    def test_legacy_and_stage_specific_request_backends_cannot_conflict(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能选择不同后端"):
            resolve_stage_backend_request(
                "local_saber",
                "ocr",
                stage_backend="fixture_remote",
                legacy_backend="local",
            )

    def test_complete_profile_can_be_registered_without_loading_a_backend(self) -> None:
        stages = {stage: "fixture_remote" for stage in PIPELINE_STAGES}
        register_pipeline_profile("fixture-remote", stages)
        try:
            profile, backend = resolve_stage_backend("fixture_remote", "render")
            self.assertEqual(profile.name, "fixture_remote")
            self.assertEqual(backend, "fixture_remote")
        finally:
            unregister_pipeline_profile("fixture_remote")


if __name__ == "__main__":
    unittest.main()
