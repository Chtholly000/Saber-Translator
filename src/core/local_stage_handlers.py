"""Lazy bridges keep local GPU imports out of remote stage routing."""

from importlib import import_module


def _lazy(module, attribute):
    def call(*args, **kwargs):
        return getattr(import_module(module), attribute)(*args, **kwargs)
    return call


get_bubble_detection_result_with_auto_directions = _lazy("src.core.detection", "get_bubble_detection_result_with_auto_directions")
recognize_ocr_results_in_bubbles = _lazy("src.core.ocr", "recognize_ocr_results_in_bubbles")
validate_manga_48_hybrid_combo = _lazy("src.core.ocr_hybrid_manga_48", "validate_manga_48_hybrid_combo")
translate_text_list = _lazy("src.core.translation", "translate_text_list")
inpaint_bubbles = _lazy("src.core.inpainting", "inpaint_bubbles")
render_bubbles_unified = _lazy("src.core.rendering", "render_bubbles_unified")
calculate_auto_font_size = _lazy("src.core.rendering", "calculate_auto_font_size")
extract_bubble_colors = _lazy("src.core.color_extractor", "extract_bubble_colors")
