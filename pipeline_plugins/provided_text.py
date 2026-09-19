"""Offline example: inject supplied text into known regions, without OCR inference.

Useful for testing a new pipeline or starting from externally extracted text.
This is deliberately named provided_text, not advertised as a recognition model.
"""

from src.core.ocr_types import OcrResult


class ProvidedTextOcr:
    def __init__(self, *, texts):
        if not isinstance(texts, list) or not all(isinstance(text, str) for text in texts):
            raise ValueError("texts must be a string list")
        self.texts = list(texts)

    def execute(self, image, bubble_coords, **options):
        if len(bubble_coords) != len(self.texts):
            raise ValueError("Supply exactly one text for each input region")
        return [OcrResult(text=text, engine="provided_text") for text in self.texts]


def build(**options):
    return ProvidedTextOcr(**options)
