"""Topic-driven page image research for Argus."""

from typing import Any, Callable, Dict, List, Optional

from .research_sources import (
    page_candidate_items,
    page_candidates,
    source_errors,
)
from .research_web import clean_text


ResearchTopicFn = Callable[..., Dict]
DiscoverPageImagesFn = Callable[..., Dict]
ImageConfidenceFn = Callable[[str, Dict, Dict], float]


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


def build_research_images(
    query: str,
    sources: Optional[List[str]],
    limit: int,
    images_per_page: int,
    timeout: int,
    research_topic: ResearchTopicFn,
    discover_page_images: DiscoverPageImagesFn,
    image_confidence: ImageConfidenceFn,
) -> Dict:
    """
    Discover image candidates by first finding relevant pages, then extracting page media.

    This is not a dedicated image-search backend. It is a dependency-free
    research workflow that preserves source page context for each image.
    """
    query = clean_text(query)
    if not query:
        return _err("query cannot be empty", code="INVALID_QUERY")

    limit = _safe_int(limit, 5, 1, 20)
    images_per_page = _safe_int(images_per_page, 5, 1, 30)
    timeout = _safe_int(timeout, 20, 3, 90)
    selected_sources = sources or ["web:tavily"]

    topic_result = research_topic(query=query, sources=selected_sources, limit=limit)
    if not topic_result.get("success"):
        return topic_result

    topic_data = topic_result.get("data") or {}
    merged_items = topic_data.get("merged") or []
    candidate_pages = page_candidates(page_candidate_items(topic_data, merged_items), limit)
    errors_by_source = source_errors(topic_data.get("sources") or {})
    page_results = []
    images = []
    seen_images = set()

    for page in candidate_pages:
        page_url = page["url"]
        page_result = discover_page_images(
            url=page_url,
            timeout=timeout,
            limit=images_per_page,
        )
        page_results.append(
            {
                "url": page_url,
                "title": page.get("title"),
                "source": page.get("source"),
                "success": bool(page_result.get("success")),
                "error": page_result.get("error"),
                "image_count": len((page_result.get("data") or {}).get("images") or []),
            }
        )
        if not page_result.get("success"):
            continue

        page_data = page_result.get("data") or {}
        page_title = page_data.get("title") or page.get("title")
        for image in page_data.get("images") or []:
            image_url = image.get("url")
            if not image_url or image_url in seen_images:
                continue
            seen_images.add(image_url)
            images.append(
                {
                    "query": query,
                    "image_url": image_url,
                    "alt": image.get("alt", ""),
                    "width": image.get("width", ""),
                    "height": image.get("height", ""),
                    "source": page.get("source"),
                    "source_page_url": page_url,
                    "source_page_title": page_title,
                    "source_page_snippet": page.get("snippet"),
                    "confidence": image_confidence(query, page, image),
                }
            )

    images.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return _ok(
        {
            "query": query,
            "sources": topic_data.get("sources") or {},
            "pages": page_results,
            "source_errors": errors_by_source,
            "images": images,
        },
        source_count=len(selected_sources),
        page_count=len(candidate_pages),
        crawled_page_count=len(page_results),
        image_count=len(images),
        source_error_count=len(errors_by_source),
    )
