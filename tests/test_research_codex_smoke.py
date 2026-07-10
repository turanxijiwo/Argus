import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_codex_smoke.py"
SPEC = importlib.util.spec_from_file_location("research_codex_smoke", SCRIPT_PATH)
research_codex_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_codex_smoke)


class ResearchCodexSmokeTest(unittest.TestCase):
    def test_summarize_topic_tracks_url_bearing_first_result(self):
        result = {
            "success": True,
            "data": {
                "merged": [{"url": "https://example.com", "title": "Example"}],
                "sources": {"codex": {"success": True}},
            },
        }

        summary = research_codex_smoke.summarize_topic(result)

        self.assertTrue(summary["success"])
        self.assertTrue(summary["first_result_has_url"])
        self.assertEqual(summary["merged_count"], 1)
        self.assertEqual(summary["source_errors"], [])

    def test_summarize_workflow_tracks_documents_and_brief(self):
        result = {
            "success": True,
            "data": {
                "documents": [{"success": True}, {"success": False}],
                "images": [{"image_url": "https://example.com/image.png"}],
                "source_errors": [{"source": "codex", "code": "PARSE_ERROR"}],
                "brief": {"content": "# Brief"},
            },
        }

        summary = research_codex_smoke.summarize_workflow(result)

        self.assertTrue(summary["success"])
        self.assertEqual(summary["document_count"], 2)
        self.assertEqual(summary["successful_document_count"], 1)
        self.assertEqual(summary["image_count"], 1)
        self.assertEqual(summary["source_error_count"], 1)
        self.assertTrue(summary["brief_included"])

    def test_smoke_passed_requires_url_and_successful_workflow_document(self):
        summary = {
            "topic": {"success": True, "first_result_has_url": True},
            "workflow": {"success": True, "successful_document_count": 1},
        }

        self.assertTrue(research_codex_smoke.smoke_passed(summary))

        summary["workflow"]["successful_document_count"] = 0
        self.assertFalse(research_codex_smoke.smoke_passed(summary))

    def test_saved_smoke_requires_ready_review_handoff(self):
        summary = {
            "save": True,
            "topic": {"success": True, "first_result_has_url": True},
            "workflow": {"success": True, "successful_document_count": 1},
            "review": {"passed": True},
        }

        self.assertTrue(research_codex_smoke.smoke_passed(summary))
        summary["review"] = {"passed": False}
        self.assertFalse(research_codex_smoke.smoke_passed(summary))

    def test_summarize_review_requires_matching_ready_handoffs(self):
        workflow_result = {"data": {"handoff": {"ready": True, "artifact_path": "output/research/codex.json"}}}
        review_result = {
            "success": True,
            "data": {
                "quality_status": "ready",
                "score": 100,
                "handoff": {
                    "schema": "argus.research.review.handoff.v1",
                    "artifact_path": "output/research/codex.json",
                },
            },
        }

        summary = research_codex_smoke.summarize_review(workflow_result, review_result)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["score"], 100)

    def test_exit_code_reports_runtime_unavailable_errors(self):
        summary = {
            "passed": False,
            "topic": {
                "source_errors": [
                    {
                        "source": "codex",
                        "code": "CODEX_SDK_ERROR",
                        "message": "sqlite state is unavailable",
                    }
                ]
            },
            "workflow": None,
        }

        self.assertEqual(research_codex_smoke.exit_code_for_summary(summary), 2)

    def test_exit_code_reports_contract_failure_for_non_runtime_errors(self):
        summary = {
            "passed": False,
            "topic": {
                "success": True,
                "first_result_has_url": False,
                "source_errors": [],
            },
            "workflow": None,
        }

        self.assertEqual(research_codex_smoke.exit_code_for_summary(summary), 3)


if __name__ == "__main__":
    unittest.main()
