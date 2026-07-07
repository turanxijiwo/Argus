"""HTTP crawl orchestration helpers for Argus research tools."""

from typing import Any, Callable, Dict, Iterable

from .research_web import fetch_html, parse_html


FetchHtml = Callable[[str, int], Dict]
ParseHtml = Callable[[str, str], Dict]
CrawlUrl = Callable[..., Dict]


def crawl_url_http(
    url: str,
    timeout: int,
    max_chars: int,
    fetch_html_func: FetchHtml,
    parse_html_func: ParseHtml,
) -> Dict:
    fetched = fetch_html_func(url, timeout)
    if not fetched.get("success"):
        return fetched

    parsed = parse_html_func(fetched["data"]["html"], fetched["data"]["final_url"])
    text = parsed["text"][:max_chars]
    return _ok(
        {
            "url": url,
            "final_url": fetched["data"]["final_url"],
            "status_code": fetched["data"]["status_code"],
            "content_type": fetched["data"]["content_type"],
            "title": parsed["title"],
            "description": parsed["description"],
            "text": text,
            "text_truncated": len(parsed["text"]) > len(text),
            "links": parsed["links"][:100],
            "images": parsed["images"][:100],
        },
        source="http",
        link_count=len(parsed["links"]),
        image_count=len(parsed["images"]),
        text_chars=len(text),
    )


def crawl_page_with_retries(
    crawl_url_func: CrawlUrl,
    url: str,
    render_js: bool,
    timeout: int,
    max_chars: int,
    retries: int,
    retriable_errors: Iterable[str],
) -> tuple:
    attempt_count = 0
    last_result = None
    retriable_error_set = set(retriable_errors)
    for _ in range(retries + 1):
        attempt_count += 1
        last_result = crawl_url_func(
            url=url,
            render_js=render_js,
            timeout=timeout,
            max_chars=max_chars,
        )
        if last_result.get("success"):
            break
        error_code = (last_result.get("error") or {}).get("code")
        if error_code not in retriable_error_set:
            break
    return last_result or _err("Crawl did not run", code="CRAWL_NOT_RUN"), attempt_count


def fetch_page_html(session: Any, url: str, timeout: int, max_html_bytes: int) -> Dict:
    return fetch_html(session, url=url, timeout=timeout, max_html_bytes=max_html_bytes)


def parse_page_html(html: str, base_url: str) -> Dict:
    return parse_html(html=html, base_url=base_url)


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_CRAWL_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
