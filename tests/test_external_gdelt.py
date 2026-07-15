import unittest
from unittest.mock import Mock

import requests

from argus_server.tools.external_apis import ExternalAPITools


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(f"HTTP {self.status_code}", response=response)


class ExternalGdeltTest(unittest.TestCase):
    def test_gdelt_normalizes_successful_articles(self):
        tools = ExternalAPITools()
        tools._get = Mock(
            return_value=FakeResponse(
                payload={
                    "articles": [
                        {
                            "title": "Research update",
                            "url": "https://example.com/research",
                            "domain": "example.com",
                            "language": "English",
                            "sourcecountry": "United States",
                            "tone": 1.5,
                            "seendate": "20260715T120000Z",
                            "socialimage": "https://example.com/image.jpg",
                        }
                    ]
                }
            )
        )

        result = tools.search_gdelt("OpenAI", max_records=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["count"], 1)
        self.assertEqual(result["data"]["articles"][0]["country"], "United States")
        self.assertEqual(tools._get.call_args.kwargs["params"]["maxrecords"], 1)

    def test_gdelt_rate_limit_preserves_retry_metadata(self):
        tools = ExternalAPITools()
        tools._get = Mock(
            return_value=FakeResponse(
                status_code=429,
                headers={"Retry-After": "45"},
            )
        )

        result = tools.search_gdelt("OpenAI", max_records=1)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "RATE_LIMITED")
        self.assertEqual(result["error"]["retry_after"], "45")
        self.assertEqual(result["error"]["source"], "gdelt")


if __name__ == "__main__":
    unittest.main()
