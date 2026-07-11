import unittest

from argus_server.tools.research_resources import ResearchResourceTools


class MisorderedPaperAPI:
    def __init__(self):
        self.arxiv_queries = []

    def search_arxiv(self, query, max_results, sort_by="submittedDate"):
        self.arxiv_queries.append((query, sort_by))
        return {
            "success": True,
            "data": {
                "papers": [
                    {
                        "id": "https://arxiv.org/abs/9999.00001",
                        "title": "An Unrelated Recent Paper",
                        "authors": ["Example Author"],
                        "published": "2026-01-01T00:00:00Z",
                        "pdf_url": "https://arxiv.org/pdf/9999.00001",
                    },
                    {
                        "id": "https://arxiv.org/abs/1706.03762",
                        "title": "Attention Is All You Need",
                        "authors": ["Ashish Vaswani"],
                        "published": "2017-06-12T00:00:00Z",
                        "pdf_url": "https://arxiv.org/pdf/1706.03762",
                    },
                ]
            },
        }

    def search_semantic_scholar(self, query, limit):
        return {"success": True, "data": {"papers": []}}

    def search_openreview(self, query, limit):
        return {"success": True, "data": {"papers": []}}

    def search_crossref(self, query, rows):
        return {"success": True, "data": {"works": []}}


class ResearchResourceRelevanceTest(unittest.TestCase):
    def test_exact_paper_title_is_ranked_first_and_sent_as_title_query(self):
        external_api = MisorderedPaperAPI()
        tool = ResearchResourceTools(external_api=external_api)

        result = tool.find_research_resource(
            "Attention Is All You Need",
            "paper",
            access="open",
            limit=2,
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            result["data"]["resources"][0]["title"],
            "Attention Is All You Need",
        )
        self.assertEqual(
            external_api.arxiv_queries[0],
            ('ti:"Attention Is All You Need"', "relevance"),
        )


if __name__ == "__main__":
    unittest.main()
