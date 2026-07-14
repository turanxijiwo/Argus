import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock

from argus_server.tools.analytics import AnalyticsTools
from argus_server.utils.errors import DataNotFoundError


class TopicTrendAnalysisTests(unittest.TestCase):
    def _make_tools(self, parser):
        tools = AnalyticsTools.__new__(AnalyticsTools)
        tools.data_service = SimpleNamespace(parser=parser)
        return tools

    def test_single_day_mentions_report_real_peak(self):
        parser = Mock()
        parser.read_all_titles_for_date.return_value = (
            {
                "weibo": {
                    "AI changes software development": {},
                    "Unrelated headline": {},
                }
            },
            {"weibo": "Weibo"},
            {},
        )
        tools = self._make_tools(parser)

        result = tools.get_topic_trend_analysis(
            topic="AI",
            date_range={"start": "2026-07-14", "end": "2026-07-14"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["total_mentions"], 1)
        self.assertEqual(result["summary"]["peak_count"], 1)
        self.assertEqual(result["summary"]["peak_time"], "2026-07-14")
        self.assertEqual(result["summary"]["change_rate"], 0)

    def test_date_range_without_data_does_not_invent_peak(self):
        parser = Mock()
        parser.read_all_titles_for_date.side_effect = DataNotFoundError("missing")
        tools = self._make_tools(parser)

        result = tools.get_topic_trend_analysis(
            topic="AI",
            date_range={"start": "2026-07-13", "end": "2026-07-14"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["total_mentions"], 0)
        self.assertEqual(result["summary"]["peak_count"], 0)
        self.assertIsNone(result["summary"]["peak_time"])
        self.assertEqual([item["count"] for item in result["data"]], [0, 0])


class PeriodComparisonTests(unittest.TestCase):
    def _compare_counts(self, period1_count, period2_count):
        tools = AnalyticsTools.__new__(AnalyticsTools)
        empty_range = (None, None)
        return tools._compare_overview(
            {
                "news_count": period1_count,
                "keywords": Counter(),
                "news": [],
            },
            {
                "news_count": period2_count,
                "keywords": Counter(),
                "news": [],
            },
            empty_range,
            empty_range,
            top_n=5,
        )["overview"]

    def test_overview_calculates_percent_from_nonzero_baseline(self):
        overview = self._compare_counts(10, 15)

        self.assertEqual(overview["count_change"], 5)
        self.assertEqual(overview["count_change_percent"], "+50.0%")

    def test_overview_marks_zero_baseline_percent_unavailable(self):
        overview = self._compare_counts(0, 15)

        self.assertEqual(overview["count_change"], 15)
        self.assertEqual(overview["count_change_percent"], "N/A")


if __name__ == "__main__":
    unittest.main()
