"""Invoke pinned MTU MangaLens bubble segmentation without OCR or translation."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image


class MangaLensBubbleSlotDetector:
    def detect(self, image: Image.Image, options: dict) -> list[dict]:
        # Import only inside the GPU worker invocation. Reuse upstream's model
        # loader and YOLO segmentation; do not copy its prediction algorithm.
        from manga_translator.utils.mangalens_detector import get_mangalens_detector

        detector = get_mangalens_detector()
        result = detector.detect(
            np.asarray(image.convert("RGB")),
            imgsz=options["image_size"],
            conf=options["confidence"],
            device="cuda",
            classes=(0,),
            return_annotated=False,
        )
        slots = []
        for region in result.detections:
            if region.class_id != 0:
                continue
            values = tuple(float(value) for value in region.xyxy)
            if not all(math.isfinite(value) for value in values):
                continue
            x1, y1, x2, y2 = values
            coords = [
                max(0, min(image.width, int(round(x1)))),
                max(0, min(image.height, int(round(y1)))),
                max(0, min(image.width, int(round(x2)))),
                max(0, min(image.height, int(round(y2)))),
            ]
            if coords[0] >= coords[2] or coords[1] >= coords[3]:
                continue
            slots.append({
                "coords": coords,
                "confidence": float(region.confidence),
            })
        return slots
