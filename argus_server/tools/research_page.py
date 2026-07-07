"""Page-level crawl and image discovery entry helpers for Argus research tools."""

from typing import Any, Callable, Dict

from .research_crawl import crawl_url_http
from .research_render import crawl_url_with_crawl4ai
from .research_web import is_http_url


FetchHtmlFn = Callable[[str, int], Dict]
ParseHtmlFn = Callable[[str, str], Dict]
CrawlUrlFn = Callable[..., Dict]


def crawl_page_url(
    url: str,
    render_js: bool,
    timeout: int,
    max_chars: int,
    fetch_html: FetchHtmlFn,
    parse_html: ParseHtmlFn,
    max_text_chars: int,
) -> Dict:
    """Fetch one URL and extract title, text, links, and image candidates."""
    if not is_http_url(url):
        return _err(
            f"Invalid URL: {url}",
            code="INVALID_URL",
            suggestion="URL must start with http:// or https://",
        )
    timeout = _safe_int(timeout, 20, 3, 90)
    max_chars = _safe_int(max_chars, 12000, 500, max_text_chars)
    if render_js:
        return crawl_url_with_crawl4ai(url=url, timeout=timeout, max_chars=max_chars)

    return crawl_url_http(
        url=url,
        timeout=timeout,
        max_chars=max_chars,
        fetch_html_func=fetch_html,
        parse_html_func=parse_html,
    )


def discover_page_images(
    url: str,
    timeout: int,
    limit: int,
    crawl_url: CrawlUrlFn,
) -> Dict:
    """Extract normalized image URLs from a page without downloading files."""
    limit = _safe_int(limit, 100, 1, 300)
    result = crawl_url(url=url, render_js=False, timeout=timeout, max_chars=500)
    if not result.get("success"):
        return result
    images = result["data"]["images"][:limit]
    return _ok(
        {
            "page_url": result["data"]["final_url"],
            "title": result["data"]["title"],
            "images": images,
        },
        source="page_images",
        count=len(images),
        requested_limit=limit,
    )


def _safe_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_TOOLKIT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
