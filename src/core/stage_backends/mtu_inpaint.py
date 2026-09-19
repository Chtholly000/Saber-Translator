"""Image/mask preparation for the inpaint port; no vendor or network imports."""

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter

from src.core.mtu_worker_contract import (
    MTU_WORKER_CONTRACT_VERSION, MtuWorkerContractError,
    _coords, _require_stage_response, decode_worker_png, encode_worker_png,
)


def build_repair_mask(image, coords, *, bubble_polygons=None, precise_mask=None,
                      user_mask=None, mask_dilate_size=0, mask_box_expand_ratio=0):
    """White repairs; black preserves. User brush wins after automatic dilation."""
    bounds = Image.new("L", image.size)
    draw = ImageDraw.Draw(bounds)
    ratio = float(mask_box_expand_ratio) / 100
    if not 0 <= ratio <= 1:
        raise ValueError("mask_box_expand_ratio 必须在 0–100 之间")
    for index, value in enumerate(coords):
        x1, y1, x2, y2 = _coords(value, "inpaint coords")
        polygon = (bubble_polygons or [])[index] if index < len(bubble_polygons or []) else None
        if polygon and not ratio:
            draw.polygon([tuple(point) for point in polygon], fill=255)
        else:
            dx, dy = (x2 - x1) * ratio / 2, (y2 - y1) * ratio / 2
            draw.rectangle((x1 - dx, y1 - dy, x2 + dx - 1, y2 + dy - 1), fill=255)
    mask = np.array(bounds)
    if precise_mask is not None:
        precise = np.asarray(precise_mask)
        if precise.shape != mask.shape:
            raise ValueError("文字 mask 尺寸与图片不符")
        if precise.size and precise.max() <= 1:
            precise = precise * 255
        mask = np.where((precise > 127) & (mask > 0), 255, 0).astype(np.uint8)
    dilation = int(mask_dilate_size)
    if not 0 <= dilation <= 128:
        raise ValueError("mask_dilate_size 必须在 0–128 之间")
    if dilation:
        mask = np.array(Image.fromarray(mask).filter(ImageFilter.MaxFilter(2 * dilation + 1)))
    if user_mask is not None:
        brush = np.asarray(user_mask)
        if brush.shape != mask.shape:
            raise ValueError("用户 mask 尺寸与图片不符")
        mask[brush > 200] = 255
        mask[brush < 50] = 0
    return Image.fromarray(mask)


class ModalMtuInpaintBackend:
    name = "modal_mtu"

    def __init__(self, client, options=None):
        self.client = client
        self.options = dict(options or {})

    def execute(self, image, bubble_coords, *, method="lama", fill_color="#FFFFFF", lama_model=None, **kwargs):
        if method not in {"lama", "solid"}:
            raise ValueError("MTU inpaint 仅支持 lama 或 solid")
        mask = build_repair_mask(image, bubble_coords, **kwargs)
        if not np.any(np.array(mask)):
            return image.copy(), None
        if method == "solid":
            filled = Image.new("RGB", image.size, ImageColor.getrgb(fill_color))
            result = Image.composite(filled, image.convert("RGB"), mask)
        else:
            response = self.client.execute({
                "contract_version": MTU_WORKER_CONTRACT_VERSION, "stage": "inpaint",
                "image": encode_worker_png(image.convert("RGB")),
                "mask": encode_worker_png(mask), "options": self.options,
            })
            _require_stage_response(response, "inpaint")
            result = decode_worker_png(response.get("image"))
            if result.size != image.size:
                raise MtuWorkerContractError("MTU inpaint 返回图片尺寸不符")
        return result, result.copy()
