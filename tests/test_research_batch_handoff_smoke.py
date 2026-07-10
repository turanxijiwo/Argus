import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_batch_handoff_smoke.py"
SPEC = importlib.util.spec_from_file_location("research_batch_handoff_smoke", SCRIPT_PATH)
research_batch_handoff_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_batch_handoff_smoke)


class ResearchBatchHandoffSmokeTest(unittest.TestCase):
    def test_summarize_batch_review_requires_selected_path_match(self):
        batch_result = {
            "success": True,
            "data": {
                "handoff": {
                    "schema": "argus.research.batch.handoff.v1",
                    "ready": True,
                    "artifact_paths": ["output/research/first.json", "output/research/second.json"],
                }
            },
        }
        review_result = {
            "success": True,
            "data": {
                "quality_status": "ready",
                "score": 100,
                "warnings": [],
                "handoff": {
                    "schema": "argus.research.review.handoff.v1",
                    "artifact_path": "output/research/second.json",
                },
            },
        }

        summary = research_batch_handoff_smoke.summarize_batch_review(batch_result, review_result, 1)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["review_score"], 100)

    def test_summarize_batch_review_rejects_missing_selected_path(self):
        summary = research_batch_handoff_smoke.summarize_batch_review(
            {"success": True, "data": {"handoff": {"artifact_paths": []}}},
            {"success": False, "error": {"code": "INVALID_HANDOFF"}},
            1,
        )

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["checks"]["selected_artifact_exists"])

    def test_exit_code_distinguishes_unavailable(self):
        self.assertEqual(research_batch_handoff_smoke.exit_code_for_summary({"passed": True}), 0)
        self.assertEqual(research_batch_handoff_smoke.exit_code_for_summary({"passed": False, "status": "unavailable"}), 2)
        self.assertEqual(research_batch_handoff_smoke.exit_code_for_summary({"passed": False, "status": "ran"}), 3)
