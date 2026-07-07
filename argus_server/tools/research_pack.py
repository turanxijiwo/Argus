"""Evidence packet construction for topic-driven research."""

from typing import Any, Callable, Dict, List, Optional

from .research_sources import (
    page_candidate_items,
    page_candidates,
    source_errors,
)
from .research_web import clean_text


ResearchTopicFn = Callable[..., Dict]
CrawlUrlFn = Callable[..., Dict]


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_TOOLKIT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


def _safe_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def pack_document_from_crawl(query: str, page: Dict, crawl_result: Dict) -> Dict:
    page_url = page["url"]
    document = {
        "query": query,
        "source": page.get("source"),
        "url": page_url,
        "title": page.get("title"),
        "snippet": page.get("snippet"),
        "score": page.get("score"),
        "success": bool(crawl_result.get("success")),
        "error": crawl_result.get("error"),
    }
    if crawl_result.get("success"):
        crawl_data = crawl_result.get("data") or {}
        document.update(
            {
                "final_url": crawl_data.get("final_url"),
                "status_code": crawl_data.get("status_code"),
                "content_type": crawl_data.get("content_type"),
                "page_title": crawl_data.get("title") or page.get("title"),
                "description": crawl_data.get("description"),
                "text": crawl_data.get("text") or "",
                "text_truncated": bool(crawl_data.get("text_truncated")),
                "links": (crawl_data.get("links") or [])[:20],
                "images": (crawl_data.get("images") or [])[:20],
            }
        )
    return document


def build_research_pack(
    query: str,
    sources: Optional[List[str]],
    limit: int,
    timeout: int,
    max_chars_per_page: int,
    research_topic: ResearchTopicFn,
    crawl_url: CrawlUrlFn,
    max_text_chars: int,
) -> Dict:
    """
    Build a compact evidence packet by searching a topic and crawling page text.

    The whole packet remains successful when individual sources or pages fail;
    those failures are preserved in source_errors and each document entry.
    """
    query = clean_text(query)
    if not query:
        return _err("query cannot be empty", code="INVALID_QUERY")

    limit = _safe_int(limit, 5, 1, 20)
    timeout = _safe_int(timeout, 20, 3, 90)
    max_chars_per_page = _safe_int(max_chars_per_page, 4000, 500, max_text_chars)
    selected_sources = sources or ["web:tavily"]

    topic_result = research_topic(query=query, sources=selected_sources, limit=limit)
    if not topic_result.get("success"):
        return topic_result

    topic_data = topic_result.get("data") or {}
    merged_items = topic_data.get("merged") or []
    candidate_pages = page_candidates(page_candidate_items(topic_data, merged_items), limit)
    errors_by_source = source_errors(topic_data.get("sources") or {})
    documents = []

    for page in candidate_pages:
        page_url = page["url"]
        crawl_result = crawl_url(
            url=page_url,
            render_js=False,
            timeout=timeout,
            max_chars=max_chars_per_page,
        )
        documents.append(pack_document_from_crawl(query, page, crawl_result))

    crawl_error_count = sum(1 for item in documents if not item.get("success"))
    skipped_item_count = max(0, len(merged_items) - len(candidate_pages))
    return _ok(
        {
            "query": query,
            "sources": topic_data.get("sources") or {},
            "source_errors": errors_by_source,
            "documents": documents,
        },
        source_count=len(selected_sources),
        candidate_count=len(candidate_pages),
        document_count=len(documents),
        crawl_error_count=crawl_error_count,
        source_error_count=len(errors_by_source),
        skipped_item_count=skipped_item_count,
        max_chars_per_page=max_chars_per_page,
    )
