import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class MtuModalRecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recipe = (REPO_ROOT / "workers" / "mtu" / "modal_app.py").read_text(
            encoding="utf-8"
        )

    def test_worker_image_contains_runtime_graphics_libraries(self) -> None:
        # MTU text-block construction imports its rendering font module, which
        # loads OpenCV and Qt libraries even for detection-only requests.
        self.assertIn('"libgl1"', self.recipe)
        self.assertIn('"libegl1"', self.recipe)
        self.assertIn('"libglib2.0-0"', self.recipe)
        self.assertIn('"libxkbcommon0"', self.recipe)
        self.assertIn('"libdbus-1-3"', self.recipe)

    def test_runtime_libraries_do_not_invalidate_the_large_cuda_layer(self) -> None:
        self.assertLess(
            self.recipe.index("uv sync --project /opt/mtu"),
            self.recipe.index('"libdbus-1-3"'),
        )

    def test_recipe_keeps_the_audited_revision_and_bounded_l4_worker(self) -> None:
        self.assertIn('REVISION = "f0307a063214f915f2b1d6e5cd3233f3bf78339f"', self.recipe)
        self.assertIn('gpu="L4"', self.recipe)
        self.assertIn("min_containers=0", self.recipe)
        self.assertIn("max_containers=1", self.recipe)
        self.assertIn("--group cuda12.6", self.recipe)


if __name__ == "__main__":
    unittest.main()
