import unittest
from unittest.mock import Mock

import requests

from argus_server.tools.external_apis import ExternalAPITools
from argus_server.tools.research_resources import ResearchResourceTools


SEARCH_OPDS = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Pride and Prejudice</title>
    <link rel="subsection" href="/ebooks/1342.opds" />
  </entry>
</feed>
"""

DETAIL_OPDS = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dcterms="http://purl.org/dc/terms/">
  <entry>
    <title>Pride and Prejudice</title>
    <author><name>Jane Austen</name></author>
    <published>1998-06-01T00:00:00+00:00</published>
    <rights>Public domain in the USA.</rights>
    <dcterms:language>en</dcterms:language>
    <link rel="http://opds-spec.org/acquisition"
          type="application/epub+zip"
          title="EPUB"
          href="https://www.gutenberg.org/ebooks/1342.epub3.images" />
  </entry>
</feed>
"""


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self.payload = payload
        self.content = content
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def get(self, url, params=None, timeout=None):
        if url.endswith("search.opds/"):
            return FakeResponse(content=SEARCH_OPDS)
        if url.endswith("/ebooks/1342.opds"):
            return FakeResponse(content=DETAIL_OPDS)
        return FakeResponse(status_code=404)


class FakeExternalAPI:
    def search_books(self, query, limit):
        return {
            "success": True,
            "data": {
                "books": [
                    {
                        "title": "Pride and Prejudice",
                        "authors": ["Jane Austen"],
                        "first_publish_year": 1813,
                        "isbn": ["9780141439518"],
                        "languages": ["eng"],
                        "ebook_access": "public",
                        "availability": {"status": "open", "is_readable": True},
                        "url": "https://openlibrary.org/works/OL66554W",
                    },
                    {
                        "title": "Modern Copyrighted Book",
                        "authors": ["Example Author"],
                        "languages": ["eng"],
                        "ebook_access": "borrowable",
                        "availability": {"is_lendable": True},
                        "url": "https://openlibrary.org/works/OL2W",
                    },
                ]
            },
        }

    def search_arxiv(self, query, max_results, sort_by="submittedDate"):
        return {
            "success": True,
            "data": {
                "papers": [
                    {
                        "id": "https://arxiv.org/abs/1706.03762",
                        "title": "Attention Is All You Need",
                        "authors": ["Ashish Vaswani"],
                        "summary": "Transformer paper",
                        "published": "2017-06-12T00:00:00Z",
                        "pdf_url": "https://arxiv.org/pdf/1706.03762",
                        "abs_url": "https://arxiv.org/abs/1706.03762",
                    }
                ]
            },
        }

    def search_semantic_scholar(self, query, limit):
        return {
            "success": True,
            "data": {
                "papers": [
                    {
                        "id": "s2-paper",
                        "title": "Attention Is All You Need",
                        "authors": ["Ashish Vaswani", "Noam Shazeer"],
                        "year": 2017,
                        "url": "https://www.semanticscholar.org/paper/s2-paper",
                        "pdf_url": "https://example.edu/attention.pdf",
                    }
                ]
            },
        }

    def search_openreview(self, query, limit):
        return {"success": True, "data": {"papers": []}}

    def search_crossref(self, query, rows):
        return {
            "success": True,
            "data": {
                "works": [
                    {
                        "doi": "10.48550/arXiv.1706.03762",
                        "title": "Attention Is All You Need",
                        "authors": ["Ashish Vaswani"],
                        "published": [[2017, 6, 12]],
                        "url": "https://doi.org/10.48550/arXiv.1706.03762",
                    }
                ]
            },
        }


class RateLimitedSemanticExternalAPI(FakeExternalAPI):
    def search_semantic_scholar(self, query, limit):
        return {
            "success": False,
            "error": {"code": "RATE_LIMITED", "message": "Try again later"},
        }


class ResearchResourceToolsTest(unittest.TestCase):
    def test_book_search_merges_open_library_and_gutenberg_files(self):
        tool = ResearchResourceTools(
            external_api=FakeExternalAPI(),
            session=FakeSession(),
        )

        result = tool.find_research_resource(
            "Pride and Prejudice",
            "book",
            language="en",
            access="open",
            limit=5,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["count"], 1)
        resource = result["data"]["resources"][0]
        self.assertEqual(resource["access"], "open_download")
        self.assertEqual(set(resource["sources"]), {"open_library", "project_gutenberg"})
        self.assertEqual(resource["file_urls"][0]["format"], "epub")
        self.assertFalse(result["data"]["policy"]["bypass_access_controls"])

    def test_paper_search_deduplicates_sources_and_keeps_open_files(self):
        tool = ResearchResourceTools(external_api=FakeExternalAPI(), session=FakeSession())

        result = tool.find_research_resource(
            "Attention Is All You Need",
            "paper",
            access="open",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["count"], 1)
        resource = result["data"]["resources"][0]
        self.assertEqual(set(resource["sources"]), {"arxiv", "semantic_scholar", "crossref"})
        self.assertEqual(resource["identifiers"]["doi"], "10.48550/arXiv.1706.03762")
        self.assertEqual(len(resource["file_urls"]), 2)

    def test_course_search_keeps_verified_official_domain_for_open_filter(self):
        captured_queries = []

        def topic_search(query, sources, limit):
            captured_queries.append(query)
            return {
                "success": True,
                "data": {
                    "sources": {"codex": {"success": True, "data": {"items": []}}},
                    "merged": [
                        {
                            "source": "codex",
                            "title": "Introduction to Algorithms",
                            "url": "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms/",
                            "snippet": "Syllabus, notes, assignments, and videos",
                            "score": 0.95,
                        },
                        {
                            "source": "codex",
                            "title": "Unverified University Page",
                            "url": "https://student.example.edu/course",
                            "snippet": "University-domain candidate without open-course verification",
                            "score": 0.4,
                        },
                    ],
                },
            }

        tool = ResearchResourceTools(
            external_api=FakeExternalAPI(),
            topic_search=topic_search,
            session=FakeSession(),
        )
        result = tool.find_research_resource(
            "algorithms",
            "course",
            institution="MIT",
            access="open",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["count"], 1)
        resource = result["data"]["resources"][0]
        self.assertEqual(resource["access"], "open_read")
        self.assertTrue(resource["metadata"]["records"]["codex"]["official_domain"])
        self.assertIn("MIT", captured_queries[0])

    def test_partial_paper_source_failure_is_reported_without_losing_results(self):
        tool = ResearchResourceTools(
            external_api=RateLimitedSemanticExternalAPI(),
            session=FakeSession(),
        )

        result = tool.find_research_resource("transformers", "paper")

        self.assertTrue(result["success"])
        self.assertGreater(result["summary"]["count"], 0)
        self.assertEqual(result["summary"]["source_error_count"], 1)
        self.assertEqual(result["data"]["source_errors"][0]["code"], "RATE_LIMITED")

    def test_invalid_resource_type_returns_structured_error(self):
        tool = ResearchResourceTools(session=FakeSession())

        result = tool.find_research_resource("demo", "video")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_RESOURCE_TYPE")

    def test_open_library_adapter_preserves_access_metadata(self):
        adapter = ExternalAPITools()
        adapter._get = Mock(
            return_value=FakeResponse(
                payload={
                    "docs": [
                        {
                            "key": "/works/OL1W",
                            "title": "Open Book",
                            "ebook_access": "public",
                            "has_fulltext": True,
                            "public_scan_b": True,
                            "ia": ["open-book"],
                            "availability": {"status": "open"},
                        }
                    ]
                }
            )
        )

        result = adapter.search_books("Open Book", limit=1)

        self.assertTrue(result["success"])
        book = result["data"]["books"][0]
        self.assertEqual(book["ebook_access"], "public")
        self.assertTrue(book["has_fulltext"])
        self.assertTrue(book["public_scan"])
        self.assertEqual(book["availability"]["status"], "open")


if __name__ == "__main__":
    unittest.main()
