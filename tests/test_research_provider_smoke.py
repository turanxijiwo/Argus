import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_provider_smoke.py"
SPEC = importlib.util.spec_from_file_location("research_provider_smoke", SCRIPT_PATH)
research_provider_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_provider_smoke)


class ResearchProviderSmokeTest(unittest.TestCase):
    def test_choose_provider_uses_first_configured_provider(self):
        env = {"EXA_API_KEY": "test-key", "TAVILY_API_KEY": "test-key"}

        provider = research_provider_smoke.choose_provider(None, env)

        self.assertEqual(provider, "tavily")

    def test_choose_provider_rejects_unconfigured_requested_provider(self):
        env = {"TAVILY_API_KEY": "test-key"}

        provider = research_provider_smoke.choose_provider("exa", env)

        self.assertIsNone(provider)

    def test_summarize_topic_tracks_url_bearing_first_result(self):
        result = {
            "success": True,
            "data": {
                "merged": [{"url": "https://example.com", "title": "Example"}],
                "sources": {"web:tavily": {"success": True}},
            },
        }

        summary = research_provider_smoke.summarize_topic(result)

        self.assertTrue(summary["success"])
        self.assertTrue(summary["first_result_has_url"])
        self.assertEqual(summary["merged_count"], 1)
        self.assertEqual(summary["source_errors"], [])

    def test_smoke_passed_requires_url_and_successful_documents(self):
        summary = {
            "topic": {"success": True, "first_result_has_url": True},
            "pack": {"success": True, "successful_document_count": 1},
            "workflow": {"success": True, "successful_document_count": 1},
        }

        self.assertTrue(research_provider_smoke.smoke_passed(summary))

        summary["workflow"]["successful_document_count"] = 0
        self.assertFalse(research_provider_smoke.smoke_passed(summary))


if __name__ == "__main__":
    unittest.main()
