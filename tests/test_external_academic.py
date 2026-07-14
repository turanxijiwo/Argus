import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from argus_server.tools.external_apis import ExternalAPITools


class FakeArxivResponse:
    def __init__(self, status_code=200, retry_after=None):
        self.status_code = status_code
        self.content = b"atom-feed"
        self.headers = {}
        if retry_after is not None:
            self.headers["Retry-After"] = str(retry_after)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP status {self.status_code}")


def _arxiv_feed():
    return SimpleNamespace(
        entries=[
            SimpleNamespace(
                id="http://arxiv.org/abs/1706.03762v7",
                title="Attention Is All You Need",
                authors=[SimpleNamespace(name="Ashish Vaswani")],
                summary="Transformer paper",
                published="2017-06-12T17:57:34Z",
                updated="2023-08-02T00:41:18Z",
                arxiv_primary_category={"term": "cs.CL"},
                tags=[SimpleNamespace(term="cs.CL")],
                links=[],
                link="https://arxiv.org/abs/1706.03762v7",
            )
        ]
    )


def _papers(count):
    return {
        "success": True,
        "summary": {"count": count},
        "data": {"papers": [{"title": f"Paper {index}"} for index in range(count)]},
    }


def _works(count):
    return {
        "success": True,
        "summary": {"count": count},
        "data": {"works": [{"title": f"Work {index}"} for index in range(count)]},
    }


def _failure(code="RATE_LIMITED", message="Source unavailable"):
    return {"success": False, "error": {"code": code, "message": message}}


class AcademicAggregateTest(unittest.TestCase):
    def _tools(self, arxiv, semantic_scholar, openalex, pubmed):
        tools = ExternalAPITools()
        tools.search_arxiv = Mock(return_value=arxiv)
        tools.search_semantic_scholar = Mock(return_value=semantic_scholar)
        tools.search_openalex = Mock(return_value=openalex)
        tools.search_pubmed = Mock(return_value=pubmed)
        return tools

    def test_complete_search_reports_all_sources_and_total(self):
        tools = self._tools(_papers(1), _papers(1), _works(1), _papers(1))

        response = tools.search_all_academic("OpenAI", per_source=3)

        self.assertTrue(response["success"])
        self.assertEqual(response["summary"]["status"], "complete")
        self.assertEqual(response["summary"]["total_papers"], 4)
        self.assertEqual(response["summary"]["successful_sources"], 4)
        self.assertEqual(response["summary"]["failed_sources"], 0)
        self.assertEqual(response["data"]["status"], "complete")
        tools.search_arxiv.assert_called_once_with("OpenAI", max_results=3)
        tools.search_semantic_scholar.assert_called_once_with("OpenAI", limit=3)
        tools.search_openalex.assert_called_once_with("OpenAI", per_page=3)
        tools.search_pubmed.assert_called_once_with("OpenAI", max_results=3)

    def test_partial_search_preserves_results_and_source_error(self):
        tools = self._tools(
            _papers(1),
            _failure("RATE_LIMITED", "Semantic Scholar limited"),
            _works(2),
            _papers(0),
        )

        response = tools.search_all_academic("OpenAI", per_source=2)

        self.assertTrue(response["success"])
        self.assertEqual(response["summary"]["status"], "partial")
        self.assertEqual(response["summary"]["total_papers"], 3)
        self.assertEqual(response["summary"]["successful_sources"], 3)
        self.assertEqual(response["summary"]["failed_sources"], 1)
        self.assertEqual(response["summary"]["empty_sources"], 1)
        self.assertEqual(response["summary"]["failed_source_names"], ["semantic_scholar"])
        self.assertEqual(response["data"]["source_counts"]["openalex"], 2)
        self.assertEqual(
            response["data"]["sources"]["semantic_scholar"]["error"]["code"],
            "RATE_LIMITED",
        )

    def test_all_source_failures_return_failed_envelope(self):
        tools = self._tools(
            _failure("NETWORK_ERROR"),
            _failure("RATE_LIMITED"),
            _failure("AUTH_REQUIRED"),
            _failure("NETWORK_ERROR"),
        )
        tools.search_arxiv = Mock(side_effect=RuntimeError("arXiv crashed"))

        response = tools.search_all_academic("OpenAI", per_source=1)

        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "ALL_SOURCES_FAILED")
        self.assertEqual(response["summary"]["status"], "failed")
        self.assertEqual(response["summary"]["failed_sources"], 4)
        self.assertEqual(
            response["data"]["sources"]["arxiv"]["error"]["code"],
            "EXTERNAL_API_ERROR",
        )

    def test_successful_empty_sources_return_no_results(self):
        tools = self._tools(_papers(0), _papers(0), _works(0), _papers(0))

        response = tools.search_all_academic("missing", per_source=1)

        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "NO_RESULTS")
        self.assertEqual(response["summary"]["status"], "empty")
        self.assertEqual(response["summary"]["empty_sources"], 4)

    def test_partial_search_without_results_returns_no_results(self):
        tools = self._tools(
            _papers(0),
            _failure("RATE_LIMITED"),
            _works(0),
            _papers(0),
        )

        response = tools.search_all_academic("missing", per_source=1)

        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "NO_RESULTS")
        self.assertEqual(response["summary"]["status"], "partial")
        self.assertEqual(response["summary"]["failed_sources"], 1)
        self.assertEqual(response["summary"]["empty_sources"], 3)


class ArxivReliabilityTest(unittest.TestCase):
    def test_success_is_cached_and_reused_across_instances(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tools = ExternalAPITools(project_root=temp_dir)
            tools._get = Mock(return_value=FakeArxivResponse())

            with patch(
                "argus_server.tools.external_apis.feedparser.parse",
                return_value=_arxiv_feed(),
            ):
                first = tools.search_arxiv("transformer", max_results=1)

            cached_tools = ExternalAPITools(project_root=temp_dir)
            cached_tools._get = Mock(side_effect=AssertionError("network should not run"))
            second = cached_tools.search_arxiv("transformer", max_results=1)

            self.assertTrue(first["success"])
            self.assertFalse(first["summary"]["cache"]["hit"])
            self.assertTrue(first["summary"]["cache"]["stored"])
            self.assertTrue(second["success"])
            self.assertTrue(second["summary"]["cache"]["hit"])
            self.assertEqual(
                second["data"]["papers"][0]["title"],
                "Attention Is All You Need",
            )
            cached_tools._get.assert_not_called()
            cache_files = list((Path(temp_dir) / "output" / "cache" / "arxiv").glob("*.json"))
            self.assertEqual(len(cache_files), 1)

    def test_corrupt_cache_falls_back_to_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tools = ExternalAPITools(project_root=temp_dir)
            params = {
                "search_query": "transformer",
                "start": 0,
                "max_results": 1,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            cache_path = tools._arxiv_cache_path(params)
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text("not-json", encoding="utf-8")
            tools._get = Mock(return_value=FakeArxivResponse())

            with patch(
                "argus_server.tools.external_apis.feedparser.parse",
                return_value=_arxiv_feed(),
            ):
                response = tools.search_arxiv("transformer", max_results=1)

            self.assertTrue(response["success"])
            self.assertFalse(response["summary"]["cache"]["hit"])
            self.assertTrue(response["summary"]["cache"]["stored"])
            tools._get.assert_called_once()

    def test_expired_cache_falls_back_to_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tools = ExternalAPITools(project_root=temp_dir)
            params = {
                "search_query": "transformer",
                "start": 0,
                "max_results": 1,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            cache_path = tools._arxiv_cache_path(params)
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(
                json.dumps({"version": 1, "cached_at": 0, "response": _papers(1)}),
                encoding="utf-8",
            )
            tools._get = Mock(return_value=FakeArxivResponse())

            with patch(
                "argus_server.tools.external_apis.feedparser.parse",
                return_value=_arxiv_feed(),
            ):
                response = tools.search_arxiv("transformer", max_results=1)

            self.assertTrue(response["success"])
            self.assertFalse(response["summary"]["cache"]["hit"])
            tools._get.assert_called_once()

    def test_short_rate_limit_retries_once_after_three_seconds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tools = ExternalAPITools(project_root=temp_dir)
            tools._get = Mock(
                side_effect=[FakeArxivResponse(429, retry_after=3), FakeArxivResponse()]
            )

            with (
                patch("argus_server.tools.external_apis.time.monotonic", return_value=100.0),
                patch("argus_server.tools.external_apis.time.sleep") as sleep,
                patch(
                    "argus_server.tools.external_apis.feedparser.parse",
                    return_value=_arxiv_feed(),
                ),
            ):
                response = tools.search_arxiv("transformer", max_results=1)

            self.assertTrue(response["success"])
            self.assertEqual(tools._get.call_count, 2)
            sleep.assert_called_once_with(3.0)

    def test_persistent_rate_limit_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tools = ExternalAPITools(project_root=temp_dir)
            tools._get = Mock(
                side_effect=[FakeArxivResponse(429), FakeArxivResponse(429)]
            )

            with (
                patch("argus_server.tools.external_apis.time.monotonic", return_value=100.0),
                patch("argus_server.tools.external_apis.time.sleep") as sleep,
            ):
                response = tools.search_arxiv("transformer", max_results=1)

            self.assertFalse(response["success"])
            self.assertEqual(response["error"]["code"], "RATE_LIMITED")
            self.assertEqual(response["error"]["attempts"], 2)
            self.assertEqual(tools._get.call_count, 2)
            sleep.assert_called_once_with(3.0)

    def test_long_retry_after_returns_without_blocking(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tools = ExternalAPITools(project_root=temp_dir)
            tools._get = Mock(return_value=FakeArxivResponse(429, retry_after=60))

            with patch("argus_server.tools.external_apis.time.sleep") as sleep:
                response = tools.search_arxiv("transformer", max_results=1)

            self.assertFalse(response["success"])
            self.assertEqual(response["error"]["code"], "RATE_LIMITED")
            self.assertEqual(response["error"]["retry_after"], "60")
            self.assertEqual(response["error"]["attempts"], 1)
            tools._get.assert_called_once()
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
