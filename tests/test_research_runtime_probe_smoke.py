import importlib.util
import pathlib
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_runtime_probe_smoke.py"
SPEC = importlib.util.spec_from_file_location("research_runtime_probe_smoke", SCRIPT_PATH)
research_runtime_probe_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_runtime_probe_smoke)


class ResearchRuntimeProbeSmokeTest(unittest.TestCase):
    def test_summarize_probe_accepts_all_verified_runtimes(self):
        result = {
            "success": True,
            "data": {"probes": {"crawl4ai": {"status": "runtime_verified"}, "codex": {"status": "runtime_verified"}}},
        }

        summary = research_runtime_probe_smoke.summarize_probe(result, ["crawl4ai", "codex"])

        self.assertTrue(summary["success"])
        self.assertEqual(summary["status"], "ready")

    def test_summarize_probe_marks_configuration_failure_blocked(self):
        result = {
            "success": True,
            "data": {"probes": {"codex": {"status": "runtime_failed", "error": {"code": "CONFIG_ERROR"}}}},
        }

        summary = research_runtime_probe_smoke.summarize_probe(result, ["codex"])

        self.assertFalse(summary["success"])
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(research_runtime_probe_smoke.exit_code_for_summary(summary), 2)

    def test_summarize_probe_marks_unexpected_failures_failed(self):
        result = {
            "success": True,
            "data": {"probes": {"crawl4ai": {"status": "runtime_failed", "error": {"code": "CRAWL4AI_ERROR"}}}},
        }

        summary = research_runtime_probe_smoke.summarize_probe(result, ["crawl4ai"])

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(research_runtime_probe_smoke.exit_code_for_summary(summary), 3)
