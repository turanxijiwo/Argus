import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_crawl_quality_smoke.py"
SPEC = importlib.util.spec_from_file_location("research_crawl_quality_smoke", SCRIPT_PATH)
research_crawl_quality_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_crawl_quality_smoke)


class ResearchCrawlQualitySmokeTest(unittest.TestCase):
    def test_summarize_fixture_passes_expected_public_page_contract(self):
        fixture = {
            "name": "example",
            "url": "https://example.com/",
            "title_contains": "Example",
            "min_text_chars": 20,
            "min_links": 1,
            "min_images": 0,
        }
        crawl_result = {
            "success": True,
            "summary": {"text_chars": 80, "link_count": 1, "image_count": 0},
            "data": {
                "final_url": "https://example.com/",
                "status_code": 200,
                "title": "Example Domain",
                "text": "Example Domain page text",
                "links": [{"url": "https://iana.org"}],
                "images": [],
            },
        }
        image_result = {
            "success": True,
            "data": {"page_url": "https://example.com/", "images": []},
        }

        summary = research_crawl_quality_smoke.summarize_fixture(
            fixture,
            crawl_result,
            image_result,
        )

        self.assertTrue(summary["passed"])
        self.assertTrue(summary["crawl"]["checks"]["title_contains"])
        self.assertTrue(summary["image_discovery"]["checks"]["min_images"])

    def test_summarize_fixture_fails_when_text_quality_is_too_low(self):
        fixture = {
            "name": "short",
            "url": "https://example.com/",
            "title_contains": "Example",
            "min_text_chars": 200,
            "min_links": 1,
            "min_images": 0,
        }
        crawl_result = {
            "success": True,
            "summary": {"text_chars": 20, "link_count": 1, "image_count": 0},
            "data": {
                "title": "Example Domain",
                "text": "short text",
                "links": [{"url": "https://iana.org"}],
                "images": [],
            },
        }
        image_result = {
            "success": True,
            "data": {"page_url": "https://example.com/", "images": []},
        }

        summary = research_crawl_quality_smoke.summarize_fixture(
            fixture,
            crawl_result,
            image_result,
        )

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["crawl"]["checks"]["min_text_chars"])

    def test_summarize_workflow_requires_successful_document_and_brief(self):
        result = {
            "success": True,
            "data": {
                "documents": [{"success": True}],
                "images": [{"image_url": "https://example.com/image.png"}],
                "source_errors": [],
                "brief": {"content": "# Brief"},
            },
        }

        summary = research_crawl_quality_smoke.summarize_workflow(result)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["successful_document_count"], 1)
        self.assertTrue(summary["checks"]["brief_included"])

    def test_summarize_workflow_fails_on_source_errors(self):
        result = {
            "success": True,
            "data": {
                "documents": [{"success": True}],
                "source_errors": [{"source": "wikipedia", "code": "NETWORK_ERROR"}],
                "brief": {"content": "# Brief"},
            },
        }

        summary = research_crawl_quality_smoke.summarize_workflow(result)

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["checks"]["no_source_errors"])

    def test_smoke_passed_requires_all_fixtures_and_workflow(self):
        summary = {
            "fixtures": [{"passed": True}, {"passed": True}],
            "workflow": {"passed": True},
        }

        self.assertTrue(research_crawl_quality_smoke.smoke_passed(summary))

        summary["fixtures"][1]["passed"] = False
        self.assertFalse(research_crawl_quality_smoke.smoke_passed(summary))

    def test_exit_code_distinguishes_unavailable_from_quality_failure(self):
        self.assertEqual(
            research_crawl_quality_smoke.exit_code_for_summary({"passed": False, "status": "unavailable"}),
            2,
        )
        self.assertEqual(
            research_crawl_quality_smoke.exit_code_for_summary({"passed": False, "status": "ran"}),
            3,
        )

    def test_selected_fixtures_filters_by_name(self):
        selected = research_crawl_quality_smoke.selected_fixtures(["example_domain"])

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["name"], "example_domain")


if __name__ == "__main__":
    unittest.main()
