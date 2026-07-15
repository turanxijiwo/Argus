import os
import unittest
from unittest.mock import Mock, patch

import requests

from argus_server.tools.external_apis import ExternalAPITools


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(f"HTTP {self.status_code}", response=response)


class ExternalAuthTest(unittest.TestCase):
    def test_github_token_is_sent_to_every_github_api_method(self):
        tools = ExternalAPITools()
        tools._get = Mock(
            side_effect=[
                FakeResponse(payload={"items": []}),
                FakeResponse(payload=[]),
                FakeResponse(payload={"items": []}),
                FakeResponse(payload=[]),
            ]
        )

        with patch.dict(os.environ, {"GITHUB_TOKEN": "github-secret"}, clear=False):
            results = [
                tools.get_github_trending(limit=1),
                tools.get_github_releases("openai/openai-python", limit=1),
                tools.search_github_code("FastMCP language:python", limit=1),
                tools.search_ghsa(per_page=1),
            ]

        self.assertTrue(all(result["success"] for result in results))
        for request_call in tools._get.call_args_list:
            headers = request_call.kwargs["headers"]
            self.assertEqual(headers["Authorization"], "Bearer github-secret")
            self.assertEqual(headers["X-GitHub-Api-Version"], "2026-03-10")

    def test_semantic_scholar_key_is_sent_in_official_header(self):
        tools = ExternalAPITools()
        tools._get = Mock(return_value=FakeResponse(payload={"data": [], "total": 0}))

        with patch.dict(
            os.environ,
            {"SEMANTIC_SCHOLAR_API_KEY": "semantic-secret"},
            clear=False,
        ):
            result = tools.search_semantic_scholar("transformers", limit=1)

        self.assertTrue(result["success"])
        self.assertEqual(tools._get.call_args.kwargs["headers"], {"x-api-key": "semantic-secret"})
        self.assertTrue(result["summary"]["authenticated"])

    def test_configured_provider_keys_report_authentication_failures(self):
        tools = ExternalAPITools()

        with patch.dict(os.environ, {"GITHUB_TOKEN": "bad-github"}, clear=False):
            tools._get = Mock(return_value=FakeResponse(status_code=401))
            github = tools.search_github_code("FastMCP language:python", limit=1)

        with patch.dict(
            os.environ,
            {"SEMANTIC_SCHOLAR_API_KEY": "bad-semantic"},
            clear=False,
        ):
            tools._get = Mock(return_value=FakeResponse(status_code=401))
            semantic = tools.search_semantic_scholar("transformers", limit=1)

        with patch.dict(os.environ, {"OPENALEX_API_KEY": "bad-openalex"}, clear=False):
            tools._get = Mock(return_value=FakeResponse(status_code=401))
            openalex = tools.search_openalex("transformers", per_page=1)

        for result in (github, semantic, openalex):
            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "AUTH_FAILED")
            self.assertNotIn("bad-", str(result))

    def test_openalex_key_is_sent_without_leaking_it_in_errors(self):
        tools = ExternalAPITools()
        tools._get = Mock(return_value=FakeResponse(payload={"results": [], "meta": {}}))

        with patch.dict(os.environ, {"OPENALEX_API_KEY": "openalex-secret"}, clear=False):
            result = tools.search_openalex("transformers", per_page=1)

        self.assertTrue(result["success"])
        self.assertEqual(tools._get.call_args.kwargs["params"]["api_key"], "openalex-secret")
        self.assertTrue(result["summary"]["authenticated"])

        tools._get = Mock(
            side_effect=requests.Timeout(
                "request failed for https://api.openalex.org/works?api_key=openalex-secret"
            )
        )
        with patch.dict(os.environ, {"OPENALEX_API_KEY": "openalex-secret"}, clear=False):
            failed = tools.search_openalex("transformers", per_page=1)

        self.assertFalse(failed["success"])
        self.assertNotIn("openalex-secret", str(failed))

    def test_reliefweb_uses_configured_appname_and_classifies_406(self):
        tools = ExternalAPITools()
        tools.session.post = Mock(return_value=FakeResponse(payload={"data": []}))

        with patch.dict(os.environ, {"RELIEFWEB_APPNAME": "approved-argus"}, clear=False):
            result = tools.search_reliefweb(query="education", limit=1)

        self.assertTrue(result["success"])
        self.assertIn("appname=approved-argus", tools.session.post.call_args.args[0])
        self.assertTrue(result["summary"]["authenticated"])

        tools.session.post = Mock(return_value=FakeResponse(status_code=406))
        with patch.dict(os.environ, {"RELIEFWEB_APPNAME": "approved-argus"}, clear=False):
            failed = tools.search_reliefweb(query="education", limit=1)

        self.assertFalse(failed["success"])
        self.assertEqual(failed["error"]["code"], "AUTH_REQUIRED")


if __name__ == "__main__":
    unittest.main()
