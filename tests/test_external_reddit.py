import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from argus_server.tools.external_apis import ExternalAPITools


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ExternalRedditTest(unittest.TestCase):
    def test_reddit_json_success_preserves_rich_fields(self):
        tools = ExternalAPITools()
        tools._get = Mock(
            return_value=FakeResponse(
                payload={
                    "data": {
                        "children": [
                            {
                                "data": {
                                    "id": "abc",
                                    "title": "JSON post",
                                    "author": "example",
                                    "score": 7,
                                    "num_comments": 3,
                                    "created_utc": 1_700_000_000,
                                    "url": "https://example.com/article",
                                    "permalink": "/r/programming/comments/abc/post/",
                                    "subreddit": "programming",
                                }
                            }
                        ]
                    }
                }
            )
        )

        result = tools.search_reddit("programming", sort="new", limit=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["transport"], "reddit_json")
        self.assertEqual(result["data"]["posts"][0]["score"], 7)
        self.assertEqual(result["data"]["posts"][0]["num_comments"], 3)

    def test_reddit_falls_back_to_atom_when_json_is_forbidden(self):
        tools = ExternalAPITools()
        tools._get = Mock(
            side_effect=[
                FakeResponse(status_code=403),
                FakeResponse(status_code=200, content=b"<feed />"),
            ]
        )
        feed = SimpleNamespace(
            entries=[
                {
                    "id": "t3_abc",
                    "title": "Atom post",
                    "link": "https://www.reddit.com/r/programming/comments/abc/post/",
                    "author": "/u/example",
                    "updated": "2026-07-14T20:08:48+00:00",
                }
            ],
            bozo=False,
        )

        with patch("argus_server.tools.external_apis.feedparser.parse", return_value=feed):
            result = tools.search_reddit("programming", sort="new", limit=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["transport"], "reddit_atom")
        self.assertEqual(result["summary"]["fallback_from"], "reddit_json")
        post = result["data"]["posts"][0]
        self.assertEqual(post["id"], "abc")
        self.assertIsNone(post["score"])
        self.assertIsNone(post["num_comments"])
        self.assertEqual(post["subreddit"], "programming")

    def test_reddit_atom_rate_limit_is_structured(self):
        tools = ExternalAPITools()
        tools._get = Mock(
            side_effect=[
                FakeResponse(status_code=403),
                FakeResponse(status_code=429, headers={"retry-after": "30"}),
            ]
        )

        result = tools.search_reddit("programming", sort="new", limit=1)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "RATE_LIMITED")
        self.assertEqual(result["error"]["retry_after"], "30")
        self.assertEqual(result["error"]["transport"], "reddit_atom")


if __name__ == "__main__":
    unittest.main()
