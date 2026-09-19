import base64
import io
import os
import sys
import unittest

import numpy as np
from PIL import Image


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.extraction_backends import (  # noqa: E402
    create_extraction_backend,
    unregister_extraction_backend,
)
from src.core.extraction_backends.mtu_modal import (  # noqa: E402
    ModalMtuExtractionBackend,
    register_modal_mtu_extraction_backend,
)
from src.core.mtu_worker_contract import (  # noqa: E402
    MTU_WORKER_CONTRACT_VERSION,
    MtuWorkerContractError,
)


def mask_payload(width: int, height: int) -> dict:
    buffer = io.BytesIO()
    Image.fromarray(np.full((height, width), 255, dtype=np.uint8)).save(buffer, format="PNG")
    return {
        "media_type": "image/png",
        "encoding": "base64",
        "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
    }


class FakeWorkerClient:
    def __init__(self) -> None:
        self.requests = []

    def execute(self, payload):
        self.requests.append(payload)
        if payload["stage"] == "detect":
            return {
                "contract_version": MTU_WORKER_CONTRACT_VERSION,
                "stage": "detect",
                "regions": [{
                    "coords": [1, 2, 9, 8],
                    "polygon": [[1, 2], [9, 2], [9, 8], [1, 8]],
                    "angle": 0,
                    "direction": "v",
                    "textlines": [{"polygon": [[1, 2], [9, 2], [9, 8], [1, 8]], "direction": "v"}],
                }],
                "text_mask": mask_payload(12, 10),
            }
        return {
            "contract_version": MTU_WORKER_CONTRACT_VERSION,
            "stage": "ocr",
            "results": [{
                "id": "region-0",
                "text": "テスト",
                "confidence": 0.91,
                "confidenceSupported": True,
                "engine": "mtu-48px",
                "primaryEngine": "mtu-48px",
                "fallbackUsed": False,
            }],
        }


class MtuWorkerAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = Image.new("RGB", (12, 10), "white")
        self.client = FakeWorkerClient()
        self.backend = ModalMtuExtractionBackend(self.client)

    def test_detect_normalizes_worker_regions_and_mask(self) -> None:
        result = self.backend.detect(self.image, detector_type="default")

        self.assertEqual(result["coords"], [[1, 2, 9, 8]])
        self.assertEqual(result["auto_directions"], ["v"])
        self.assertEqual(result["raw_mask"].shape, (10, 12))
        request = self.client.requests[0]
        self.assertEqual(request["contract_version"], MTU_WORKER_CONTRACT_VERSION)
        self.assertEqual(request["stage"], "detect")
        self.assertEqual(request["image"]["width"], 12)
        # UI-local model names never control the isolated worker's model choice.
        self.assertEqual(request["options"], {})

    def test_ocr_preserves_request_order_and_returns_saber_result(self) -> None:
        results = self.backend.ocr(
            self.image,
            [[1, 2, 9, 8]],
            source_language="japanese",
            ocr_engine="48px",
            textlines_per_bubble=[[]],
        )

        self.assertEqual(results[0].text, "テスト")
        self.assertTrue(results[0].confidence_supported)
        request = self.client.requests[0]
        self.assertEqual(request["stage"], "ocr")
        self.assertEqual(request["regions"][0]["id"], "region-0")
        self.assertNotIn("baidu_api_key", request["options"])

    def test_sensitive_ocr_options_fail_before_the_worker_is_called(self) -> None:
        with self.assertRaises(MtuWorkerContractError):
            self.backend.ocr(
                self.image,
                [[1, 2, 9, 8]],
                baidu_api_key="not-forwarded",
            )
        self.assertEqual(self.client.requests, [])

    def test_missing_ocr_region_fails_instead_of_shortening_results(self) -> None:
        class IncompleteWorker:
            def execute(self, _payload):
                return {
                    "contract_version": MTU_WORKER_CONTRACT_VERSION,
                    "stage": "ocr",
                    "results": [],
                }

        backend = ModalMtuExtractionBackend(IncompleteWorker())
        with self.assertRaisesRegex(MtuWorkerContractError, "缺少区域结果"):
            backend.ocr(self.image, [[1, 2, 9, 8]])

    def test_injected_backend_can_be_registered_without_modal_imports(self) -> None:
        register_modal_mtu_extraction_backend(self.client)
        try:
            backend = create_extraction_backend(
                "modal_mtu",
                local_detect=lambda *_args, **_kwargs: {},
                local_ocr=lambda *_args, **_kwargs: [],
            )
            self.assertEqual(backend.name, "modal_mtu")
        finally:
            unregister_extraction_backend("modal_mtu")


if __name__ == "__main__":
    unittest.main()
