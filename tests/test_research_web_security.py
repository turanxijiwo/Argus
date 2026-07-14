import asyncio
import socket
import unittest
from unittest.mock import patch

from argus_server.tools.research_render import crawl_url_with_crawl4ai
from argus_server.tools.research_network import fetch_html, validate_public_http_url


PUBLIC_ADDRESS = "93.184.216.34"


def public_dns_result(host, port, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_ADDRESS, port))]


class FakeResponse:
    def __init__(self, url, status_code=200, headers=None, body=b"<h1>Public page</h1>"):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.body = body
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


class FakeRequest:
    def __init__(self, url):
        self.url = url


class FakeRoute:
    def __init__(self, url):
        self.request = FakeRequest(url)
        self.aborted = False
        self.continued = False

    async def abort(self, error_code=None):
        self.aborted = True

    async def continue_(self):
        self.continued = True


class FakePage:
    def __init__(self):
        self.route_handler = None

    async def route(self, pattern, handler):
        self.route_handler = handler


class FakeStrategy:
    def __init__(self):
        self.hook = None

    def set_hook(self, hook_type, hook):
        if hook_type == "on_page_context_created":
            self.hook = hook


class FakeCrawlResult:
    success = True
    url = "https://example.com"
    status_code = 200
    redirected_status_code = None
    response_headers = {"content-type": "text/html"}
    metadata = {"title": "Public page"}
    cleaned_html = "<h1>Public page</h1>"
    markdown = None
    links = {}
    media = {}


class RedirectingFakeCrawler:
    last_route = None

    def __init__(self, *args, **kwargs):
        self.crawler_strategy = FakeStrategy()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def arun(self, url, config):
        page = FakePage()
        if self.crawler_strategy.hook:
            await self.crawler_strategy.hook(page, context=None, config=config)
        route = FakeRoute("http://169.254.169.254/latest/meta-data")
        self.__class__.last_route = route
        if page.route_handler:
            await page.route_handler(route)
        return FakeCrawlResult()


class ResearchWebSecurityTest(unittest.TestCase):
    @patch.dict("os.environ", {"CODEX_SANDBOX": "seatbelt"})
    @patch(
        "socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.83", 443))],
    )
    def test_url_validation_allows_codex_virtual_dns_for_hostname(self, _resolve):
        result = validate_public_http_url("https://example.com/article")

        self.assertTrue(result["success"])

    @patch.dict("os.environ", {"CODEX_SANDBOX": "seatbelt"})
    def test_fetch_html_rejects_explicit_codex_virtual_address(self):
        session = FakeSession([])

        result = fetch_html(session, "http://198.18.0.83/admin", timeout=10, max_html_bytes=1024)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_URL")
        self.assertEqual(session.calls, [])

    @patch("socket.getaddrinfo", side_effect=public_dns_result)
    def test_fetch_html_allows_public_target(self, _resolve):
        response = FakeResponse("https://example.com/article")
        session = FakeSession([response])

        result = fetch_html(session, "https://example.com/article", timeout=10, max_html_bytes=1024)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["html"], "<h1>Public page</h1>")
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(session.calls[0]["allow_redirects"])
        self.assertTrue(response.closed)

    def test_fetch_html_rejects_loopback_before_request(self):
        session = FakeSession([])

        result = fetch_html(session, "http://127.0.0.1/admin", timeout=10, max_html_bytes=1024)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_URL")
        self.assertEqual(session.calls, [])

    @patch("socket.getaddrinfo", side_effect=public_dns_result)
    def test_fetch_html_rejects_redirect_to_link_local_target(self, _resolve):
        redirect = FakeResponse(
            "https://example.com/start",
            status_code=302,
            headers={"location": "http://169.254.169.254/latest/meta-data"},
            body=b"",
        )
        session = FakeSession([redirect])

        result = fetch_html(session, "https://example.com/start", timeout=10, max_html_bytes=1024)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_URL")
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(redirect.closed)

    @patch("crawl4ai.AsyncWebCrawler", RedirectingFakeCrawler)
    @patch("socket.getaddrinfo", side_effect=public_dns_result)
    def test_crawl4ai_rejects_private_redirect_request(self, _resolve):
        RedirectingFakeCrawler.last_route = None

        result = crawl_url_with_crawl4ai("https://example.com", timeout=10, max_chars=1000)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_URL")
        self.assertTrue(RedirectingFakeCrawler.last_route.aborted)
        self.assertFalse(RedirectingFakeCrawler.last_route.continued)


if __name__ == "__main__":
    unittest.main()
