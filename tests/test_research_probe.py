import unittest

from argus_server.tools.research_probe import build_research_runtime_probe


class ResearchRuntimeProbeTest(unittest.TestCase):
    def test_probe_reports_verified_optional_runtimes(self):
        result = build_research_runtime_probe(
            adapters=["crawl4ai", "codex"],
            url="https://example.com",
            query="OpenAI",
            timeout=10,
            crawl_url=lambda **kwargs: {"success": True, "data": {"text": "Rendered", "images": []}},
            codex_search=lambda **kwargs: {"success": True, "data": {"items": [{"url": "https://example.com"}]}},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["runtime_verified_count"], 2)
        self.assertEqual(result["data"]["probes"]["crawl4ai"]["status"], "runtime_verified")
        self.assertTrue(result["data"]["probes"]["codex"]["first_result_has_url"])

    def test_probe_sanitizes_codex_configuration_failures(self):
        result = build_research_runtime_probe(
            adapters=["codex"],
            url="https://example.com",
            query="OpenAI",
            timeout=10,
            crawl_url=lambda **kwargs: {},
            codex_search=lambda **kwargs: {
                "success": False,
                "error": {
                    "code": "CODEX_SDK_ERROR",
                    "message": "failed to load configuration: /private/user/config.toml: unknown variant `ultra`",
                },
            },
        )

        probe = result["data"]["probes"]["codex"]
        self.assertEqual(probe["status"], "runtime_failed")
        self.assertEqual(probe["error"]["code"], "CONFIG_ERROR")
        self.assertNotIn("/private/user", probe["error"]["message"])

    def test_probe_rejects_unknown_adapters(self):
        result = build_research_runtime_probe(
            adapters=["unknown"],
            url="https://example.com",
            query="OpenAI",
            timeout=10,
            crawl_url=lambda **kwargs: {},
            codex_search=lambda **kwargs: {},
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_ADAPTERS")
