import os
import tempfile
import unittest
from unittest.mock import patch

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


class ResearchToolkitToolsTest(unittest.TestCase):
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

    def test_download_gallery_rejects_output_outside_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = ResearchToolkitTools(project_root=tmpdir)
            with patch("argus_server.tools.research_toolkit.shutil.which", return_value="/usr/bin/gallery-dl"):
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
            with patch("argus_server.tools.research_toolkit.shutil.which", return_value="/usr/bin/gallery-dl"):
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


if __name__ == "__main__":
    unittest.main()
