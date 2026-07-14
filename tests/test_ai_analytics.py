import unittest
from unittest.mock import Mock

from argus_server.tools.ai_analytics import AIAnalyticsTools


def _success(label):
    return {"success": True, "summary": {"label": label}, "data": {"label": label}}


def _failure(code, message="Step unavailable"):
    return {"success": False, "error": {"code": code, "message": message}}


class AnalyzeWithAITest(unittest.TestCase):
    def _tools(self, dedup, anomaly):
        tools = AIAnalyticsTools()
        tools.semantic_deduplicate = Mock(return_value=dedup)
        tools.detect_anomaly = Mock(return_value=anomaly)
        return tools

    def test_full_mode_reports_complete_when_both_steps_succeed(self):
        tools = self._tools(_success("dedup"), _success("anomaly"))
        news_items = [{"title": "OpenAI update"}]

        response = tools.analyze_with_ai(
            news_items=news_items,
            topic="OpenAI",
            mode="full",
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["summary"]["status"], "complete")
        self.assertEqual(response["summary"]["steps_attempted"], 2)
        self.assertEqual(response["summary"]["successful_steps"], 2)
        self.assertEqual(response["summary"]["failed_steps"], 0)
        self.assertEqual(response["data"]["status"], "complete")
        tools.semantic_deduplicate.assert_called_once_with(news_items)
        tools.detect_anomaly.assert_called_once_with(topic="OpenAI")

    def test_full_mode_reports_partial_and_preserves_step_error(self):
        tools = self._tools(
            _success("dedup"),
            _failure("NO_LOCAL_DATA", "No history"),
        )

        response = tools.analyze_with_ai(
            news_items=[{"title": "OpenAI update"}],
            mode="full",
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["summary"]["status"], "partial")
        self.assertEqual(response["summary"]["successful_steps"], 1)
        self.assertEqual(response["summary"]["failed_steps"], 1)
        self.assertEqual(response["summary"]["failed_step_names"], ["anomaly"])
        self.assertEqual(response["data"]["status"], "partial")
        self.assertEqual(
            response["data"]["anomaly"]["error"]["code"],
            "NO_LOCAL_DATA",
        )

    def test_full_mode_reports_failure_when_all_steps_fail(self):
        tools = self._tools(
            _failure("AUTH_REQUIRED", "No AI provider"),
            _failure("NO_LOCAL_DATA", "No history"),
        )
        tools.detect_anomaly = Mock(side_effect=RuntimeError("storage crashed"))

        response = tools.analyze_with_ai(
            news_items=[{"title": "OpenAI update"}],
            mode="full",
        )

        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "ALL_STEPS_FAILED")
        self.assertEqual(response["summary"]["status"], "failed")
        self.assertEqual(response["summary"]["successful_steps"], 0)
        self.assertEqual(response["summary"]["failed_steps"], 2)
        self.assertEqual(response["summary"]["failed_step_names"], ["dedup", "anomaly"])
        self.assertEqual(
            response["data"]["anomaly"]["error"]["code"],
            "ANALYSIS_ERROR",
        )

    def test_dedup_mode_failure_is_not_reported_as_success(self):
        tools = self._tools(
            _failure("AUTH_REQUIRED", "No AI provider"),
            _success("anomaly"),
        )

        response = tools.analyze_with_ai(
            news_items=[{"title": "OpenAI update"}],
            mode="dedup",
        )

        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "ALL_STEPS_FAILED")
        self.assertEqual(response["summary"]["steps_attempted"], 1)
        self.assertEqual(response["summary"]["failed_step_names"], ["dedup"])
        tools.detect_anomaly.assert_not_called()

    def test_anomaly_mode_success_only_runs_anomaly_step(self):
        tools = self._tools(_success("dedup"), _success("anomaly"))

        response = tools.analyze_with_ai(topic="OpenAI", mode="anomaly")

        self.assertTrue(response["success"])
        self.assertEqual(response["summary"]["status"], "complete")
        self.assertEqual(response["summary"]["steps_attempted"], 1)
        self.assertNotIn("dedup", response["data"])
        tools.semantic_deduplicate.assert_not_called()
        tools.detect_anomaly.assert_called_once_with(topic="OpenAI")

    def test_invalid_mode_returns_invalid_param_without_running_steps(self):
        tools = self._tools(_success("dedup"), _success("anomaly"))

        response = tools.analyze_with_ai(mode="unknown")

        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "INVALID_PARAM")
        tools.semantic_deduplicate.assert_not_called()
        tools.detect_anomaly.assert_not_called()


if __name__ == "__main__":
    unittest.main()
