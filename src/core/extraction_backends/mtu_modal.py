"""Injected-client adapter for detection/OCR executed by a pinned MTU worker."""

from typing import Any, Dict, List, Mapping, Protocol

from src.core.mtu_worker_contract import (
    build_mtu_detect_request,
    build_mtu_ocr_request,
    normalize_mtu_detect_response,
    normalize_mtu_ocr_response,
)

from .base import ExtractionBackend, LocalExtractionFunctions
from .registry import register_extraction_backend


class MtuWorkerClient(Protocol):
    """Transport supplied by deployment code; it may wrap Modal, HTTP, or tests."""

    def execute(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Execute a versioned worker request without exposing transport objects."""


class ModalMtuDetectorBackend:
    """MTU detector port; does not require an OCR implementation."""

    name = "modal_mtu"

    def __init__(self, worker_client: MtuWorkerClient, model_options=None):
        self._worker_client = worker_client
        self._model_options = model_options

    def execute(self, image: Any, **options: Any) -> Dict[str, Any]:
        request_payload = build_mtu_detect_request(image, options)
        if self._model_options is not None:
            request_payload["options"] = dict(self._model_options.get("detect", {}))
        response_payload = self._worker_client.execute(request_payload)
        return normalize_mtu_detect_response(
            response_payload,
            image_width=image.width,
            image_height=image.height,
        )


class ModalMtuOcrBackend:
    """MTU OCR port; does not require a detector implementation."""

    name = "modal_mtu"

    def __init__(self, worker_client: MtuWorkerClient, model_options=None):
        self._worker_client = worker_client
        self._model_options = model_options

    def execute(
        self,
        image: Any,
        bubble_coords: List[Any],
        **options: Any,
    ) -> List[Any]:
        request_payload = build_mtu_ocr_request(image, bubble_coords, options)
        if self._model_options is not None:
            request_payload["options"] = {**self._model_options.get("ocr", {}),
                                          "source_language": options.get("source_language", "japanese")}
        response_payload = self._worker_client.execute(request_payload)
        return normalize_mtu_ocr_response(
            response_payload,
            expected_region_ids=[region["id"] for region in request_payload["regions"]],
        )


class ModalMtuExtractionBackend:
    """Compatibility facade; new code selects the independent stage ports."""

    name = "modal_mtu"

    def __init__(self, worker_client: MtuWorkerClient, model_options=None):
        self._detector = ModalMtuDetectorBackend(worker_client, model_options)
        self._ocr = ModalMtuOcrBackend(worker_client, model_options)

    def detect(self, image, **options):
        return self._detector.execute(image, **options)

    def ocr(self, image, bubble_coords, **options):
        return self._ocr.execute(image, bubble_coords, **options)


def register_modal_mtu_extraction_backend(
    worker_client: MtuWorkerClient,
    *,
    replace: bool = False,
) -> None:
    """Register an injected worker client without importing Modal or loading MTU."""

    def factory(_local_functions: LocalExtractionFunctions) -> ExtractionBackend:
        return ModalMtuExtractionBackend(worker_client)

    register_extraction_backend("modal_mtu", factory, replace=replace)
