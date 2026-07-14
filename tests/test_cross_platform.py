import unittest
from types import SimpleNamespace
from unittest.mock import patch

from argus_server.tools.cross_platform import CrossPlatformTools


class HackerNewsExternal:
    def __init__(self):
        self.search_calls = []

    def search_hackernews(self, query, hits):
        self.search_calls.append({"query": query, "hits": hits})
        return {
            "success": True,
            "data": {
                "hits": [
                    {
                        "title": "OpenAI research update",
                        "url": "https://example.com/openai",
                        "author": "alice",
                        "points": 5,
                        "num_comments": 2,
                    }
                ]
            },
        }


class EmptyNewsSearch:
    def search_news_unified(self, query, limit):
        return {"success": True, "data": {"hot_list": []}}


class RecordingCLI:
    def __init__(self):
        self.calls = []

    def run_xhs(self, subcommand, args, timeout):
        self.calls.append(("xhs", subcommand, args, timeout))
        return {
            "success": True,
            "data": {"notes": [{"title": "OpenAI note", "url": "https://xhs.example/note"}]},
        }

    def run_bilibili(self, subcommand, args, timeout):
        self.calls.append(("bili", subcommand, args, timeout))
        return {
            "success": True,
            "data": {"results": [{"title": "OpenAI video", "bvid": "BV1"}]},
        }

    def run_twitter(self, subcommand, args, timeout):
        self.calls.append(("twitter", subcommand, args, timeout))
        return {
            "success": True,
            "data": {"tweets": [{"text": "OpenAI post", "url": "https://x.example/post"}]},
        }

    def run_telegram(self, subcommand, args, timeout):
        self.calls.append(("tg", subcommand, args, timeout))
        return {
            "success": True,
            "data": {"messages": [{"text": "OpenAI message", "link": "https://t.me/post"}]},
        }

    def run_discord(self, subcommand, args, timeout):
        self.calls.append(("discord", subcommand, args, timeout))
        return {
            "success": True,
            "data": {"messages": [{"content": "OpenAI message", "link": "https://discord.com/post"}]},
        }


class FailingCLI:
    @staticmethod
    def _failure():
        return {
            "success": False,
            "error": {"code": "AUTH_REQUIRED", "message": "Login required"},
        }

    def run_xhs(self, subcommand, args, timeout):
        return self._failure()

    def run_bilibili(self, subcommand, args, timeout):
        return self._failure()

    def run_twitter(self, subcommand, args, timeout):
        return self._failure()

    def run_telegram(self, subcommand, args, timeout):
        return self._failure()

    def run_discord(self, subcommand, args, timeout):
        return self._failure()


class CrossPlatformToolsTest(unittest.TestCase):
    def test_hackernews_uses_hits_parameter_and_normalizes_algolia_fields(self):
        external = HackerNewsExternal()
        tools = CrossPlatformTools(external_api=external)

        search_response = tools.universal_search("OpenAI", sources=["hn"], limit=3)

        self.assertTrue(search_response["success"])
        self.assertEqual(search_response["summary"]["status"], "complete")
        self.assertEqual(external.search_calls, [{"query": "OpenAI", "hits": 3}])
        item = search_response["data"]["merged"][0]
        self.assertEqual(item["author"], "alice")
        self.assertEqual(item["engagement"], 7)

    def test_cli_search_arguments_match_each_documented_command(self):
        cli = RecordingCLI()
        tools = CrossPlatformTools(cli_adapter=cli)
        expected_arguments = {
            "xhs": ["OpenAI"],
            "bili": ["OpenAI", "-n", "3"],
            "twitter": ["OpenAI", "-n", "3"],
            "tg": ["OpenAI"],
            "discord": ["OpenAI"],
        }

        for source, expected in expected_arguments.items():
            with self.subTest(source=source):
                source_response = tools._fetch_source(source, "OpenAI", 3)
                self.assertEqual(source_response.get("error"), None)
                self.assertEqual(cli.calls[-1][2], expected)

    def test_cli_search_failures_preserve_structured_error(self):
        tools = CrossPlatformTools(cli_adapter=FailingCLI())

        for source in ("xhs", "bili", "twitter", "tg", "discord"):
            with self.subTest(source=source):
                source_response = tools._fetch_source(source, "OpenAI", 3)
                self.assertEqual(source_response["error"], "Login required")
                self.assertEqual(source_response["error_code"], "AUTH_REQUIRED")

    def test_reddit_uses_atom_search_and_preserves_rate_metadata(self):
        response = SimpleNamespace(
            status_code=200,
            content=b"<feed />",
            headers={
                "x-ratelimit-limit": "10",
                "x-ratelimit-remaining": "9",
                "x-ratelimit-reset": "60",
            },
            raise_for_status=lambda: None,
        )
        feed = SimpleNamespace(
            entries=[
                {
                    "title": "OpenAI discussion",
                    "link": "https://www.reddit.com/r/OpenAI/comments/abc/topic/",
                    "author": "/u/example",
                }
            ],
            bozo=False,
        )
        tools = CrossPlatformTools()

        with patch("requests.get", return_value=response) as get, patch(
            "feedparser.parse", return_value=feed
        ):
            source_response = tools._fetch_source("reddit", "OpenAI", 3)

        self.assertEqual(source_response.get("error"), None)
        self.assertEqual(len(source_response["items"]), 1)
        self.assertEqual(source_response["items"][0]["source"], "reddit:r/OpenAI")
        self.assertEqual(source_response["meta"]["transport"], "reddit_atom")
        self.assertEqual(source_response["meta"]["rate_limit"]["remaining"], "9")
        self.assertEqual(get.call_args.kwargs["params"]["q"], "OpenAI")

    def test_reddit_rate_limit_returns_failed_envelope(self):
        response = SimpleNamespace(
            status_code=429,
            content=b"",
            headers={"retry-after": "30"},
            raise_for_status=lambda: None,
        )
        tools = CrossPlatformTools()

        with patch("requests.get", return_value=response):
            search_response = tools.universal_search(
                "OpenAI", sources=["reddit"], limit=3
            )

        self.assertFalse(search_response["success"])
        self.assertEqual(search_response["error"]["code"], "ALL_SOURCES_FAILED")
        reddit = search_response["data"]["sources"]["reddit"]
        self.assertEqual(reddit["error_code"], "RATE_LIMITED")
        self.assertEqual(reddit["meta"]["rate_limit"]["retry_after"], "30")

    def test_all_source_failures_return_failed_envelope_with_diagnostics(self):
        tools = CrossPlatformTools()

        search_response = tools.universal_search("OpenAI", sources=["hn", "xhs"], limit=2)

        self.assertFalse(search_response["success"])
        self.assertEqual(search_response["error"]["code"], "ALL_SOURCES_FAILED")
        self.assertEqual(search_response["summary"]["status"], "failed")
        self.assertEqual(search_response["summary"]["failed_sources"], 2)
        self.assertEqual(search_response["data"]["sources"]["hn"]["status"], "failed")
        self.assertEqual(search_response["data"]["sources"]["xhs"]["status"], "failed")

    def test_zero_results_from_successful_source_returns_no_results(self):
        tools = CrossPlatformTools(search_tools=EmptyNewsSearch())

        search_response = tools.universal_search("missing", sources=["news"], limit=2)

        self.assertFalse(search_response["success"])
        self.assertEqual(search_response["error"]["code"], "NO_RESULTS")
        self.assertEqual(search_response["summary"]["status"], "empty")
        self.assertEqual(search_response["summary"]["empty_sources"], 1)
        self.assertEqual(search_response["data"]["sources"]["news"]["status"], "empty")

    def test_partial_search_keeps_items_and_reports_failed_sources(self):
        tools = CrossPlatformTools(external_api=HackerNewsExternal())

        search_response = tools.universal_search(
            "OpenAI", sources=["hn", "xhs"], limit=2
        )

        self.assertTrue(search_response["success"])
        self.assertEqual(search_response["summary"]["status"], "partial")
        self.assertEqual(search_response["summary"]["failed_sources"], 1)
        self.assertEqual(search_response["summary"]["total_items"], 1)
        self.assertEqual(search_response["data"]["sources"]["hn"]["status"], "ready")
        self.assertEqual(search_response["data"]["sources"]["xhs"]["status"], "failed")

    def test_narrative_tracking_propagates_failed_and_partial_search_status(self):
        failed_tools = CrossPlatformTools()
        partial_tools = CrossPlatformTools(external_api=HackerNewsExternal())

        failed_response = failed_tools.narrative_tracking(
            "OpenAI", platforms=["hn"], use_llm=False
        )
        partial_response = partial_tools.narrative_tracking(
            "OpenAI", platforms=["hn", "xhs"], use_llm=False
        )

        self.assertFalse(failed_response["success"])
        self.assertEqual(failed_response["error"]["code"], "ALL_SOURCES_FAILED")
        self.assertTrue(partial_response["success"])
        self.assertEqual(partial_response["summary"]["status"], "partial")
        self.assertEqual(partial_response["data"]["status"], "partial")
        self.assertEqual(partial_response["summary"]["failed_sources"], 1)


if __name__ == "__main__":
    unittest.main()
