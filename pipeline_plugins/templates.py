"""Copy the ONE class needed by your plugin; implement its execute method.

Classes are also factories: ``your_package:Ocr`` with JSON constructor options.
These templates fail explicitly until a real implementation is supplied.
Heavy dependencies belong in __init__ (lazy factory execution), never at module
import. Optional close() releases model/client resources on process shutdown.
See docs/STAGE_PLUGINS.md for exact output shapes and model configuration.
"""


class Detector:
    def __init__(self, **options):
        self.options = options

    def execute(self, image, **options):
        """Return {coords, angles?, polygons?, auto_directions?, textlines_per_bubble?, raw_mask?}."""
        raise NotImplementedError("Implement detection and normalize to original pixels")


class Ocr:
    def __init__(self, **options):
        self.options = options

    def execute(self, image, bubble_coords, *, source_language="japanese", textlines_per_bubble=None):
        """Return one src.core.ocr_types.OcrResult per input region, in order."""
        raise NotImplementedError("Call your OCR model and preserve empty regions")


class Color:
    def __init__(self, **options):
        self.options = options

    def execute(self, image, bubble_coords, textlines_per_bubble=None):
        """Return [{fg_color: [r,g,b] or None, bg_color: [r,g,b] or None}, ...]."""
        raise NotImplementedError("Extract colors for each region")


class Translator:
    def __init__(self, **options):
        self.options = options

    def execute(self, texts, *, target_language, prompt_content=None):
        """Return list[str] of identical length/order, preserving placeholders."""
        raise NotImplementedError("Call your translator and align results")


class Inpainter:
    def __init__(self, **options):
        self.options = options

    def execute(self, image, bubble_coords, **options):
        """Return (PIL result image, PIL clean background or None), same size."""
        raise NotImplementedError("Honor explicit user masks and repair image")


class Renderer:
    def __init__(self, **options):
        self.options = options

    def execute(self, image, bubble_states, *, auto_font_size=False):
        """Return same-size PIL image; update normalized styles in bubble_states."""
        raise NotImplementedError("Implement layout/typesetting; honor auto_font_size")
