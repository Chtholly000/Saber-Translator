import subprocess
import sys
import unittest

import numpy as np
from PIL import Image

from tools.typeset import typeset


class TypesetClientTests(unittest.TestCase):
    def test_renders_supplied_text_on_blank_image_without_inference(self):
        image = Image.new("RGB", (300, 100), "white")
        layout = {"bubble_states": [{"bubbleId": "generated-caption", "coords": [10, 10, 290, 90],
                                    "translatedText": "Hello", "fontSize": 24,
                                    "fontFamily": "fonts/Arial_Unicode.ttf", "textDirection": "horizontal"}]}
        result = typeset(image, layout)
        self.assertLess(np.asarray(result).min(), 255)
        self.assertEqual(np.asarray(image).min(), 255)
        self.assertEqual(layout["bubble_states"][0]["translatedText"], "Hello")

    def test_entrypoint_does_not_import_gpu_modules(self):
        command = "import sys; from tools.typeset import typeset; assert not any(n == 'torch' or n.startswith('manga_translator') or n == 'modal' for n in sys.modules)"
        result = subprocess.run([sys.executable, "-c", command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
