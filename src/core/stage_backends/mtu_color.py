"""Optional color extraction port using the same MTU worker's 48px model."""

from src.core.mtu_worker_contract import (
    build_mtu_ocr_request, normalize_mtu_ocr_response, _require_stage_response,
    MtuWorkerContractError,
)


class ModalMtuColorBackend:
    name = "modal_mtu"

    def __init__(self, client):
        self.client = client

    def execute(self, image, coords, textlines_per_bubble=None):
        payload = build_mtu_ocr_request(image, coords, {"textlines_per_bubble": textlines_per_bubble or []})
        payload.update(stage="color", options={})
        response = self.client.execute(payload)
        _require_stage_response(response, "color")
        ids = [region["id"] for region in payload["regions"]]
        normalize_mtu_ocr_response({**response, "stage": "ocr"}, expected_region_ids=ids)
        items = {value["id"]: value for value in response["results"]}
        results = []
        for ident in ids:
            item = items[ident]
            colors = {}
            for channel in ("fg_color", "bg_color"):
                value = item.get(channel)
                if value is not None and (not isinstance(value, list) or len(value) != 3
                                          or any(type(v) is not int or not 0 <= v <= 255 for v in value)):
                    raise MtuWorkerContractError("MTU 返回无效颜色")
                colors[channel] = value
            results.append(colors)
        return results
