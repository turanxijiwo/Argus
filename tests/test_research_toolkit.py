import json
import os
import tempfile
import unittest
from unittest.mock import patch

from argus_server.tools.research_runtime import default_workflow_sources
from argus_server.tools.research_toolkit import ResearchToolkitTools


class FakeExternalAPI:
    def search_hackernews(self, query, hits):
        return {
            "success": True,
            "data": {
                "hits": [
                    {
                        "title": f"{query} launch",
                        "url": "https://example.com/hn",
                        "comment_text": "HN discussion",
                        "points": 42,
                    }
                ]
            },
        }

    def search_wikipedia(self, query, limit):
        return {
            "success": True,
            "data": {
                "articles": [
                    {
                        "title": query,
                        "url": "https://example.com/wiki",
                        "snippet": "Wiki summary",
                        "wordcount": 100,
                    }
                ]
            },
        }


class FakeAIWebSearch:
    def ai_web_search(self, query, provider, max_results, include_answer, search_depth):
        return {
            "success": True,
            "summary": {"provider": provider, "count": 1},
            "data": {
                "answer": f"{query} web answer",
                "results": [
                    {
                        "title": f"{query} field report",
                        "url": "https://example.com/web",
                        "content": "Web result snippet",
                        "score": 0.87,
                    }
                ],
                "query": query,
            },
        }


class FakeMultiPageAIWebSearch:
    def ai_web_search(self, query, provider, max_results, include_answer, search_depth):
        return {
            "success": True,
            "summary": {"provider": provider, "count": 2},
            "data": {
                "results": [
                    {
                        "title": f"{query} first page",
                        "url": "https://example.com/first",
                        "content": "First image source page",
                        "score": 0.6,
                    },
                    {
                        "title": f"{query} second page",
                        "url": "https://example.com/second",
                        "content": "Second image source page",
                        "score": 0.5,
                    },
                ],
                "query": query,
            },
        }


class FakeMarkdown:
    raw_markdown = "# Rendered Title\nRendered body from browser"
    fit_markdown = None
    markdown_with_citations = None


class FakeCrawl4AIResult:
    success = True
    url = "https://example.com/rendered"
    status_code = 200
    redirected_status_code = None
    response_headers = {"content-type": "text/html; charset=utf-8"}
    metadata = {"title": "Rendered Title", "description": "Rendered desc"}
    cleaned_html = """
    <html>
      <body>
        <h1>Rendered Title</h1>
        <a href="https://example.com/page">Rendered link</a>
        <img src="/rendered.png" alt="Rendered image">
      </body>
    </html>
    """
    markdown = FakeMarkdown()
    links = {
        "internal": [{"href": "https://example.com/page", "text": "Rendered link"}],
        "external": [],
    }
    media = {
        "images": [{"src": "/rendered.png", "alt": "Rendered image"}],
    }


class ResearchToolkitToolsTest(unittest.TestCase):
    def test_toolkit_health_reports_missing_optional_capabilities(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())

        with patch("argus_server.tools.research_health.shutil.which", return_value=None), \
                patch("argus_server.tools.research_health.importlib.util.find_spec", return_value=None), \
                patch.dict(os.environ, {
                    "TAVILY_API_KEY": "",
                    "EXA_API_KEY": "",
                    "PERPLEXITY_API_KEY": "",
                    "BRAVE_API_KEY": "",
                }, clear=False):
            result = tool.toolkit_health()

        self.assertTrue(result["success"])
        capabilities = result["data"]["capabilities"]
        self.assertTrue(capabilities["crawl_url"]["can_use_now"])
        self.assertFalse(capabilities["crawl_url_render_js"]["can_use_now"])
        self.assertEqual(capabilities["crawl_url_render_js"]["missing"], ["crawl4ai"])
        self.assertFalse(capabilities["research_topic_web"]["can_use_now"])
        self.assertEqual(capabilities["research_topic_web"]["status"], "needs_api_key")
        self.assertFalse(capabilities["research_topic_codex"]["can_use_now"])
        self.assertEqual(capabilities["research_topic_codex"]["missing"], ["openai-codex"])
        self.assertFalse(capabilities["research_pack"]["can_use_now"])
        self.assertFalse(capabilities["research_workflow"]["can_use_now"])
        self.assertFalse(capabilities["research_batch_workflow"]["can_use_now"])
        self.assertTrue(capabilities["find_research_resource"]["can_use_now"])
        self.assertEqual(
            capabilities["find_research_resource"]["resource_types"]["paper"],
            "needs_external_adapter",
        )
        self.assertEqual(
            capabilities["find_research_resource"]["resource_types"]["course"],
            "needs_codex_runtime",
        )
        self.assertFalse(result["data"]["optional_cli"]["gallery-dl"]["installed"])
        self.assertFalse(result["data"]["optional_cli"]["openai-codex"]["installed"])

    def test_toolkit_health_marks_configured_web_provider_ready(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())

        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            result = tool.toolkit_health()

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["api_providers"]["tavily"]["configured"])
        self.assertTrue(result["data"]["capabilities"]["research_topic_web"]["can_use_now"])
        self.assertEqual(result["data"]["capabilities"]["research_topic_web"]["available_sources"], ["web:tavily"])
        self.assertTrue(result["data"]["capabilities"]["research_pack"]["can_use_now"])
        self.assertTrue(result["data"]["capabilities"]["research_workflow"]["can_use_now"])
        self.assertTrue(result["data"]["capabilities"]["research_batch_workflow"]["can_use_now"])

    def test_toolkit_health_marks_codex_runner_ready(self):
        tool = ResearchToolkitTools(
            project_root=os.getcwd(),
            codex_runner=lambda query, limit: {"items": []},
        )

        result = tool.toolkit_health()

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["capabilities"]["research_topic_codex"]["can_use_now"])
        self.assertEqual(result["data"]["capabilities"]["research_topic_codex"]["status"], "ready")
        self.assertTrue(result["data"]["adapters"]["codex_runner_attached"])

    def test_default_workflow_sources_prefer_configured_web_then_codex_then_public_sources(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False), \
                patch("argus_server.tools.research_runtime.importlib.util.find_spec", return_value=None):
            self.assertEqual(default_workflow_sources(ai_search=FakeAIWebSearch()), ["web:tavily"])

        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False), \
                patch("argus_server.tools.research_runtime.importlib.util.find_spec", return_value=None):
            self.assertEqual(default_workflow_sources(codex_runner=lambda query, limit: "{}"), ["codex"])
            self.assertEqual(default_workflow_sources(), ["local_news", "hackernews", "wikipedia"])

    def test_crawl_url_extracts_text_links_and_images(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())
        html = """
        <html>
          <head><title>Demo Page</title><meta name="description" content="Demo desc"></head>
          <body>
            <h1>Hello Argus</h1>
            <a href="/next">Next page</a>
            <img src="/image.png" alt="Hero">
          </body>
        </html>
        """
        tool._fetch_html = lambda url, timeout: {
            "success": True,
            "data": {
                "html": html,
                "final_url": "https://example.com/base",
                "status_code": 200,
                "content_type": "text/html",
            },
        }

        result = tool.crawl_url("https://example.com/base")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["title"], "Demo Page")
        self.assertIn("Hello Argus", result["data"]["text"])
        self.assertEqual(result["data"]["links"][0]["url"], "https://example.com/next")
        self.assertEqual(result["data"]["images"][0]["url"], "https://example.com/image.png")

    def test_crawl_url_rejects_invalid_url(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())

        result = tool.crawl_url("file:///etc/passwd")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_URL")

    def test_crawl_url_render_js_reports_missing_crawl4ai(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())

        with patch("argus_server.tools.research_render.importlib.util.find_spec", return_value=None):
            result = tool.crawl_url("https://example.com/base", render_js=True)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NOT_INSTALLED")
        self.assertEqual(result["error"]["install_hint"], "uv pip install crawl4ai && crawl4ai-setup")

    def test_crawl_url_formats_crawl4ai_result(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())

        result = tool._format_crawl4ai_result(
            url="https://example.com/base",
            result=FakeCrawl4AIResult(),
            max_chars=500,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["source"], "crawl4ai")
        self.assertEqual(result["data"]["final_url"], "https://example.com/rendered")
        self.assertEqual(result["data"]["title"], "Rendered Title")
        self.assertIn("Rendered body from browser", result["data"]["text"])
        self.assertEqual(result["data"]["links"][0]["url"], "https://example.com/page")
        self.assertEqual(result["data"]["images"][0]["url"], "https://example.com/rendered.png")

    def test_download_gallery_rejects_output_outside_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            with patch("argus_server.tools.research_gallery.shutil.which", return_value="/usr/bin/gallery-dl"):
                result = tool.download_gallery(
                    target="https://example.com/gallery",
                    output_dir="/tmp/outside-argus",
                    confirm=False,
                )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_OUTPUT_DIR")

    def test_download_gallery_returns_dry_run_when_installed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            with patch("argus_server.tools.research_gallery.shutil.which", return_value="/usr/bin/gallery-dl"):
                result = tool.download_gallery(
                    target="https://example.com/gallery",
                    output_dir="output/media",
                    confirm=False,
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["mode"], "dry_run")
        self.assertTrue(result["data"]["confirm_required"])
        self.assertEqual(result["data"]["command"], ["/usr/bin/gallery-dl", "https://example.com/gallery"])

    def test_research_topic_normalizes_sources(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), external_api=FakeExternalAPI())

        result = tool.research_topic("AI browser", sources=["hackernews", "wikipedia"], limit=2)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["source_count"], 2)
        self.assertEqual(len(result["data"]["merged"]), 2)
        self.assertEqual(result["data"]["merged"][0]["source"], "wikipedia")

    def test_research_topic_normalizes_web_source(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())

        result = tool.research_topic("AI browser", sources=["web:tavily"], limit=2)

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["sources"]["web:tavily"]["success"])
        self.assertEqual(result["data"]["sources"]["web:tavily"]["summary"]["provider"], "tavily")
        self.assertEqual(len(result["data"]["merged"]), 2)
        self.assertEqual(result["data"]["merged"][0]["title"], "tavily answer: AI browser")
        self.assertEqual(result["data"]["merged"][1]["url"], "https://example.com/web")

    def test_research_topic_reports_missing_web_adapter(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())

        result = tool.research_topic("AI browser", sources=["web:brave"], limit=2)

        self.assertTrue(result["success"])
        self.assertFalse(result["data"]["sources"]["web:brave"]["success"])
        self.assertEqual(result["data"]["sources"]["web:brave"]["error"]["code"], "ADAPTER_UNAVAILABLE")

    def test_research_topic_normalizes_codex_runner_source(self):
        def fake_codex_runner(query, limit):
            return json.dumps({
                "items": [
                    {
                        "title": f"{query} field notes",
                        "url": "https://example.com/codex",
                        "snippet": "Codex supplied a public source.",
                        "score": 0.91,
                    }
                ]
            })

        tool = ResearchToolkitTools(project_root=os.getcwd(), codex_runner=fake_codex_runner)

        result = tool.research_topic("AI browser", sources=["codex"], limit=2)

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["sources"]["codex"]["success"])
        self.assertEqual(result["data"]["sources"]["codex"]["summary"]["runner"], "injected")
        self.assertEqual(result["data"]["merged"][0]["source"], "codex")
        self.assertEqual(result["data"]["merged"][0]["url"], "https://example.com/codex")

    def test_research_topic_reports_missing_codex_sdk(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())

        with patch("argus_server.tools.research_source_ai.importlib.util.find_spec", return_value=None):
            result = tool.research_topic("AI browser", sources=["codex"], limit=2)

        self.assertTrue(result["success"])
        self.assertFalse(result["data"]["sources"]["codex"]["success"])
        self.assertEqual(result["data"]["sources"]["codex"]["error"]["code"], "NOT_INSTALLED")
        self.assertEqual(result["data"]["sources"]["codex"]["error"]["install_hint"], "uv pip install openai-codex")

    def test_research_pack_crawls_topic_pages(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        tool.crawl_url = lambda url, render_js, timeout, max_chars: {
            "success": True,
            "summary": {"source": "http"},
            "data": {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
                "title": "AI browser field report",
                "description": "Demo page description",
                "text": "Evidence text about AI browser workflows.",
                "text_truncated": False,
                "links": [{"url": "https://example.com/next", "text": "Next"}],
                "images": [{"url": "https://example.com/image.png", "alt": "Preview"}],
            },
        }

        result = tool.research_pack(
            "AI browser",
            sources=["web:tavily"],
            limit=2,
            max_chars_per_page=1200,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["document_count"], 1)
        self.assertEqual(result["summary"]["crawl_error_count"], 0)
        document = result["data"]["documents"][0]
        self.assertTrue(document["success"])
        self.assertEqual(document["source"], "web:tavily")
        self.assertEqual(document["url"], "https://example.com/web")
        self.assertIn("Evidence text", document["text"])
        self.assertEqual(document["page_title"], "AI browser field report")

    def test_research_pack_preserves_crawl_errors(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        tool.crawl_url = lambda url, render_js, timeout, max_chars: {
            "success": False,
            "error": {
                "code": "NETWORK_ERROR",
                "message": "Request failed",
                "url": url,
            },
        }

        result = tool.research_pack("AI browser", sources=["web:tavily"], limit=2)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["document_count"], 1)
        self.assertEqual(result["summary"]["crawl_error_count"], 1)
        document = result["data"]["documents"][0]
        self.assertFalse(document["success"])
        self.assertEqual(document["error"]["code"], "NETWORK_ERROR")
        self.assertEqual(document["url"], "https://example.com/web")

    def test_research_pack_uses_web_result_when_answer_has_no_url_at_limit_one(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        crawled_urls = []

        def fake_crawl(url, render_js, timeout, max_chars):
            crawled_urls.append(url)
            return {
                "success": True,
                "data": {
                    "url": url,
                    "final_url": url,
                    "status_code": 200,
                    "content_type": "text/html",
                    "title": "AI browser field report",
                    "description": "",
                    "text": "Evidence text.",
                    "text_truncated": False,
                    "links": [],
                    "images": [],
                },
            }

        tool.crawl_url = fake_crawl

        result = tool.research_pack("AI browser", sources=["web:tavily"], limit=1)

        self.assertTrue(result["success"])
        self.assertEqual(crawled_urls, ["https://example.com/web"])
        self.assertEqual(result["summary"]["document_count"], 1)
        self.assertEqual(result["data"]["documents"][0]["url"], "https://example.com/web")

    def test_research_workflow_builds_and_saves_packet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir, ai_search=FakeAIWebSearch())
            tool.crawl_url = lambda url, render_js, timeout, max_chars: {
                "success": True,
                "summary": {"source": "http"},
                "data": {
                    "url": url,
                    "final_url": url,
                    "status_code": 200,
                    "content_type": "text/html",
                    "title": "AI browser field report",
                    "description": "Demo page description",
                    "text": "Evidence text about AI browser workflows.",
                    "text_truncated": False,
                    "links": [{"url": "https://example.com/next", "text": "Next"}],
                    "images": [
                        {
                            "url": "https://example.com/image.png",
                            "alt": "AI browser screenshot",
                            "width": "1200",
                        }
                    ],
                },
            }

            result = tool.research_workflow(
                "AI browser",
                sources=["web:tavily"],
                limit=2,
                save=True,
                output_dir="output/research",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["summary"]["document_count"], 1)
            self.assertEqual(result["summary"]["crawl_error_count"], 0)
            self.assertEqual(result["summary"]["image_count"], 1)
            self.assertTrue(result["summary"]["brief_included"])
            self.assertTrue(result["summary"]["brief_saved"])
            self.assertEqual(
                result["summary"]["handoff_schema"],
                "argus.research.workflow.handoff.v1",
            )
            handoff = result["data"]["handoff"]
            self.assertTrue(handoff["ready"])
            self.assertEqual(handoff["status"], "ready")
            self.assertEqual(handoff["artifact_path"].split(os.sep, 1)[0], "output")
            self.assertEqual(handoff["brief_path"].split(os.sep, 1)[0], "output")
            self.assertNotIn(tmpdir, json.dumps(handoff))
            artifact_path = result["data"]["artifact"]["path"]
            brief_path = result["data"]["brief"]["artifact"]["path"]
            self.assertTrue(artifact_path.startswith(tmpdir))
            self.assertTrue(brief_path.startswith(tmpdir))
            self.assertTrue(os.path.exists(artifact_path))
            self.assertTrue(os.path.exists(brief_path))
            with open(artifact_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            with open(brief_path, "r", encoding="utf-8") as handle:
                brief = handle.read()
            self.assertEqual(saved["query"], "AI browser")
            self.assertEqual(saved["documents"][0]["page_title"], "AI browser field report")
            self.assertEqual(saved["images"][0]["image_url"], "https://example.com/image.png")
            self.assertIn("# Research Brief: AI browser", brief)
            self.assertIn("AI browser field report", brief)
            self.assertIn("Image Candidates", brief)

    def test_research_workflow_can_skip_brief_payload(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        tool.crawl_url = lambda url, render_js, timeout, max_chars: {
            "success": True,
            "data": {
                "url": url,
                "final_url": url,
                "status_code": 200,
                "content_type": "text/html",
                "title": "AI browser field report",
                "description": "",
                "text": "Evidence text.",
                "text_truncated": False,
                "links": [],
                "images": [],
            },
        }

        result = tool.research_workflow(
            "AI browser",
            sources=["web:tavily"],
            limit=2,
            include_brief=False,
        )

        self.assertTrue(result["success"])
        self.assertFalse(result["summary"]["brief_included"])
        self.assertIsNone(result["data"]["brief"])
        self.assertFalse(result["data"]["handoff"]["ready"])
        self.assertEqual(result["data"]["handoff"]["status"], "partial")
        self.assertIsNone(result["data"]["handoff"]["artifact_path"])
        self.assertIsNone(result["data"]["handoff"]["brief_path"])

    def test_research_review_artifact_returns_compact_quality_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            path = os.path.join(tmpdir, "output", "research", "review.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({
                    "query": "OpenAI",
                    "sources": {"wikipedia": {}},
                    "source_errors": [],
                    "brief": {"content": "brief " * 50},
                    "images": [{"image_url": "https://example.com/image.png"}],
                    "documents": [{"success": True, "text": "evidence " * 100}],
                }, handle)

            result = tool.research_review_artifact("output/research/review.json")

            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["quality_status"], "ready")
            self.assertEqual(result["data"]["score"], 100)
            self.assertEqual(result["data"]["path"], "output/research/review.json")
            self.assertTrue(result["data"]["handoff"]["ready"])
            self.assertEqual(result["data"]["handoff"]["schema"], "argus.research.review.handoff.v1")
            self.assertNotIn("evidence evidence", json.dumps(result))

    def test_research_review_artifact_rejects_outside_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            result = tool.research_review_artifact("/tmp/outside-research.json")

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "UNSAFE_ARTIFACT_PATH")

    def test_research_review_artifact_consumes_workflow_handoff(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            path = os.path.join(tmpdir, "output", "research", "handoff.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"query": "OpenAI", "sources": {}, "documents": [], "images": []}, handle)

            result = tool.research_review_artifact(
                handoff={"schema": "argus.research.workflow.handoff.v1", "artifact_path": "output/research/handoff.json"}
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["path"], "output/research/handoff.json")
            self.assertEqual(result["data"]["quality_status"], "needs_attention")

    def test_research_review_artifact_consumes_batch_handoff_by_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            for name in ("first.json", "second.json"):
                path = os.path.join(tmpdir, "output", "research", name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump({"query": name, "sources": {}, "documents": [], "images": []}, handle)

            result = tool.research_review_artifact(
                handoff={
                    "schema": "argus.research.batch.handoff.v1",
                    "artifact_paths": ["output/research/first.json", "output/research/second.json"],
                },
                artifact_index=1,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["data"]["path"], "output/research/second.json")

    def test_research_review_artifact_rejects_batch_handoff_missing_selected_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            result = tool.research_review_artifact(
                handoff={"schema": "argus.research.batch.handoff.v1", "artifact_paths": []}
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "INVALID_HANDOFF")

    def test_research_workflow_preserves_crawl_errors_after_retries(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        attempts = []

        def failing_crawl(url, render_js, timeout, max_chars):
            attempts.append(url)
            return {
                "success": False,
                "error": {
                    "code": "NETWORK_ERROR",
                    "message": "Request failed",
                    "url": url,
                },
            }

        tool.crawl_url = failing_crawl

        result = tool.research_workflow("AI browser", sources=["web:tavily"], limit=2, retries=1)

        self.assertTrue(result["success"])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(result["summary"]["crawl_error_count"], 1)
        document = result["data"]["documents"][0]
        self.assertFalse(document["success"])
        self.assertEqual(document["crawl_attempts"], 2)
        self.assertEqual(document["error"]["code"], "NETWORK_ERROR")

    def test_research_workflow_uses_web_result_when_answer_has_no_url_at_limit_one(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        crawled_urls = []

        def fake_crawl(url, render_js, timeout, max_chars):
            crawled_urls.append(url)
            return {
                "success": True,
                "data": {
                    "url": url,
                    "final_url": url,
                    "status_code": 200,
                    "content_type": "text/html",
                    "title": "AI browser field report",
                    "description": "",
                    "text": "Evidence text.",
                    "text_truncated": False,
                    "links": [],
                    "images": [
                        {
                            "url": "https://example.com/image.png",
                            "alt": "AI browser screenshot",
                        }
                    ],
                },
            }

        tool.crawl_url = fake_crawl

        result = tool.research_workflow(
            "AI browser",
            sources=["web:tavily"],
            limit=1,
            include_brief=False,
        )

        self.assertTrue(result["success"])
        self.assertEqual(crawled_urls, ["https://example.com/web"])
        self.assertEqual(result["summary"]["document_count"], 1)
        self.assertEqual(result["summary"]["image_count"], 1)
        self.assertEqual(result["data"]["documents"][0]["url"], "https://example.com/web")

    def test_research_workflow_rejects_output_outside_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir, ai_search=FakeAIWebSearch())

            result = tool.research_workflow(
                "AI browser",
                sources=["web:tavily"],
                save=True,
                output_dir="/tmp/outside-argus",
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_OUTPUT_DIR")

    def test_research_batch_workflow_saves_relative_artifacts_and_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir, ai_search=FakeAIWebSearch())
            evidence_text = "Evidence text about AI browser workflows. " * 30
            tool.crawl_url = lambda url, render_js, timeout, max_chars: {
                "success": True,
                "data": {
                    "url": url,
                    "final_url": url,
                    "status_code": 200,
                    "content_type": "text/html",
                    "title": "AI browser field report",
                    "description": "",
                    "text": evidence_text,
                    "text_truncated": False,
                    "links": [],
                    "images": [
                        {
                            "url": "https://example.com/image.png",
                            "alt": "AI browser screenshot",
                        }
                    ],
                },
            }

            result = tool.research_batch_workflow(
                ["AI browser", "AI browser", "AI safety"],
                sources=["web:tavily"],
                limit=1,
                output_dir="output/research/batch",
                report_path="output/research/artifact-reviews/batch-review.md",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["summary"]["query_count"], 2)
            self.assertEqual(result["summary"]["artifact_count"], 2)
            self.assertEqual(result["data"]["review"]["status_counts"], {"ready": 2})
            self.assertEqual(len(result["data"]["runs"]), 2)
            self.assertEqual(len(result["data"]["artifact_paths"]), 2)
            self.assertTrue(result["data"]["report_artifact"]["success"])
            self.assertEqual(
                result["data"]["report_artifact"]["data"]["path"],
                "output/research/artifact-reviews/batch-review.md",
            )
            handoff = result["data"]["handoff"]
            self.assertEqual(handoff["schema"], "argus.research.batch.handoff.v1")
            self.assertEqual(handoff["entrypoint"], "mcp")
            self.assertTrue(handoff["ready"])
            self.assertIsNone(handoff["exit_code"])
            self.assertEqual(handoff["artifact_paths"], result["data"]["artifact_paths"])
            self.assertEqual(handoff["review_report"], "output/research/artifact-reviews/batch-review.md")
            for run in result["data"]["runs"]:
                self.assertTrue(run["artifact_path"].startswith("output/research/batch/"))
                self.assertTrue(run["brief_path"].startswith("output/research/batch/"))
                self.assertEqual(run["quality_status"], "ready")
            serialized = json.dumps(result, ensure_ascii=False)
            self.assertNotIn(tmpdir, serialized)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "output/research/artifact-reviews/batch-review.md")))

    def test_research_batch_workflow_rejects_empty_queries(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())

        result = tool.research_batch_workflow(["", "   "], sources=["web:tavily"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_QUERIES")

    def test_research_batch_workflow_accepts_single_query_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir, ai_search=FakeAIWebSearch())
            tool.crawl_url = lambda url, render_js, timeout, max_chars: {
                "success": True,
                "data": {
                    "url": url,
                    "final_url": url,
                    "status_code": 200,
                    "content_type": "text/html",
                    "title": "AI browser field report",
                    "description": "",
                    "text": "Evidence text about AI browser workflows. " * 30,
                    "text_truncated": False,
                    "links": [],
                    "images": [],
                },
            }

            result = tool.research_batch_workflow("AI browser", sources=["web:tavily"])

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["query_count"], 1)
        self.assertEqual(result["data"]["queries"], ["AI browser"])

    def test_research_batch_workflow_rejects_report_outside_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir, ai_search=FakeAIWebSearch())
            tool.crawl_url = lambda url, render_js, timeout, max_chars: {
                "success": True,
                "data": {
                    "url": url,
                    "final_url": url,
                    "status_code": 200,
                    "content_type": "text/html",
                    "title": "AI browser field report",
                    "description": "",
                    "text": "Evidence text about AI browser workflows. " * 30,
                    "text_truncated": False,
                    "links": [],
                    "images": [],
                },
            }

            result = tool.research_batch_workflow(
                ["AI browser"],
                sources=["web:tavily"],
                report_path="/tmp/argus-batch-review.md",
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_REPORT_PATH")

    def test_research_images_discovers_page_images(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        tool.discover_page_images = lambda url, timeout, limit: {
            "success": True,
            "summary": {"count": 1},
            "data": {
                "page_url": url,
                "title": "AI browser gallery",
                "images": [
                    {
                        "url": "https://example.com/ai-browser.png",
                        "alt": "AI browser screenshot",
                        "width": "1200",
                        "height": "800",
                    }
                ],
            },
        }

        result = tool.research_images("AI browser", sources=["web:tavily"], limit=2, images_per_page=2)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["page_count"], 1)
        self.assertEqual(result["summary"]["image_count"], 1)
        image = result["data"]["images"][0]
        self.assertEqual(image["image_url"], "https://example.com/ai-browser.png")
        self.assertEqual(image["source_page_url"], "https://example.com/web")
        self.assertEqual(image["source"], "web:tavily")
        self.assertGreater(image["confidence"], 0.8)

    def test_research_images_uses_web_result_when_answer_has_no_url_at_limit_one(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeAIWebSearch())
        crawled_urls = []

        def fake_discover(url, timeout, limit):
            crawled_urls.append(url)
            return {
                "success": True,
                "data": {
                    "page_url": url,
                    "title": "AI browser gallery",
                    "images": [
                        {
                            "url": "https://example.com/ai-browser.png",
                            "alt": "AI browser screenshot",
                        }
                    ],
                },
            }

        tool.discover_page_images = fake_discover

        result = tool.research_images("AI browser", sources=["web:tavily"], limit=1)

        self.assertTrue(result["success"])
        self.assertEqual(crawled_urls, ["https://example.com/web"])
        self.assertEqual(result["summary"]["page_count"], 1)
        self.assertEqual(result["summary"]["image_count"], 1)
        self.assertEqual(result["data"]["images"][0]["source_page_url"], "https://example.com/web")

    def test_research_images_dedupes_across_pages(self):
        tool = ResearchToolkitTools(project_root=os.getcwd(), ai_search=FakeMultiPageAIWebSearch())
        tool.discover_page_images = lambda url, timeout, limit: {
            "success": True,
            "summary": {"count": 1},
            "data": {
                "page_url": url,
                "title": f"Images for {url}",
                "images": [
                    {
                        "url": "https://cdn.example.com/shared.png",
                        "alt": "Shared AI browser image",
                    }
                ],
            },
        }

        result = tool.research_images("AI browser", sources=["web:tavily"], limit=2, images_per_page=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["page_count"], 2)
        self.assertEqual(result["summary"]["image_count"], 1)
        self.assertEqual(result["data"]["images"][0]["source_page_url"], "https://example.com/first")

    def test_research_images_preserves_source_errors(self):
        tool = ResearchToolkitTools(project_root=os.getcwd())

        result = tool.research_images("AI browser", sources=["web:brave"], limit=2)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["page_count"], 0)
        self.assertEqual(result["summary"]["image_count"], 0)
        self.assertEqual(result["summary"]["source_error_count"], 1)
        self.assertEqual(result["data"]["source_errors"][0]["code"], "ADAPTER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
