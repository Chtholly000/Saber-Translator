import json
import pathlib
import unittest
from unittest.mock import patch

import httpx

from src.core.stage_backends.deepseek import DeepSeekTranslationBackend
from src.shared.ai_providers import get_provider_manifest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class DeepSeekAdapterTests(unittest.TestCase):
    def test_current_endpoint_and_examples_use_supported_flash_model(self) -> None:
        manifest = get_provider_manifest("deepseek")
        self.assertEqual(manifest.default_base_url, "https://api.deepseek.com")
        self.assertEqual(manifest.default_models["chat"], "deepseek-flash")
        self.assertIn("deepseek-flash", manifest.model_catalogs["vlm"])

        for relative in (
            "workers/mtu/config.example.json",
            "pipeline_plugins/mtu.example.json",
        ):
            content = (REPO_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('"model": "deepseek-flash"', content)
            self.assertNotIn('"model": "deepseek-chat"', content)

    def test_translation_uses_non_thinking_json_request_and_preserves_ids(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["authorization"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "translations": [
                                            {"id": "2", "text": "第二句"},
                                            {"id": "0", "text": "第一句"},
                                        ]
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
            )

        backend = DeepSeekTranslationBackend(
            model="deepseek-flash",
            api_key_env="SABER_TEST_DEEPSEEK_KEY",
            transport=httpx.MockTransport(handler),
        )
        with patch.dict("os.environ", {"SABER_TEST_DEEPSEEK_KEY": "fixture-secret"}):
            result = backend.execute(
                ["一つ目", "", "二つ目"],
                target_language="Simplified Chinese",
                prompt_content="Use concise manga dialogue.",
            )

        self.assertEqual(result, ["第一句", "", "第二句"])
        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer fixture-secret")
        self.assertEqual(captured["body"]["model"], "deepseek-flash")
        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})
        self.assertFalse(captured["body"]["stream"])
        self.assertIn("valid JSON object", captured["body"]["messages"][0]["content"])
        self.assertEqual(
            json.loads(captured["body"]["messages"][1]["content"])["texts"],
            [{"id": "0", "text": "一つ目"}, {"id": "2", "text": "二つ目"}],
        )

    def test_transport_failure_does_not_expose_provider_or_secret_details(self) -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(401, text="rejected fixture-secret")
        )
        backend = DeepSeekTranslationBackend(
            model="deepseek-flash",
            api_key_env="SABER_TEST_DEEPSEEK_KEY",
            transport=transport,
        )
        with patch.dict("os.environ", {"SABER_TEST_DEEPSEEK_KEY": "fixture-secret"}):
            with self.assertRaisesRegex(RuntimeError, "DeepSeek 调用失败") as raised:
                backend.execute(["source"], target_language="Simplified Chinese")
        self.assertNotIn("fixture-secret", str(raised.exception))
        self.assertNotIn("401", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
