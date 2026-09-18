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


class ModalMtuExtractionBackend:
    """Synchronous adapter used by current Flask routes after client injection."""

    name = "modal_mtu"

    def __init__(self, worker_client: MtuWorkerClient):
        self._worker_client = worker_client

    def detect(self, image: Any, **options: Any) -> Dict[str, Any]:
        request_payload = build_mtu_detect_request(image, options)
        response_payload = self._worker_client.execute(request_payload)
        return normalize_mtu_detect_response(
            response_payload,
            image_width=image.width,
            image_height=image.height,
        )

    def ocr(
        self,
        image: Any,
        bubble_coords: List[Any],
        **options: Any,
    ) -> List[Any]:
        request_payload = build_mtu_ocr_request(image, bubble_coords, options)
        response_payload = self._worker_client.execute(request_payload)
        return normalize_mtu_ocr_response(
            response_payload,
            expected_region_ids=[region["id"] for region in request_payload["regions"]],
        )


def register_modal_mtu_extraction_backend(
    worker_client: MtuWorkerClient,
    *,
    replace: bool = False,
) -> None:
    """Register an injected worker client without importing Modal or loading MTU."""

    def factory(_local_functions: LocalExtractionFunctions) -> ExtractionBackend:
        return ModalMtuExtractionBackend(worker_client)

    register_extraction_backend("modal_mtu", factory, replace=replace)
