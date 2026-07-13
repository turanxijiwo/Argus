"""Direct and page-derived image research for Argus."""

from typing import Any, Callable, Dict, List, Optional

import requests

from .research_runtime import create_research_session
from .research_sources import (
    page_candidate_items,
    page_candidates,
    source_errors,
)
from .research_web import clean_text, is_http_url


ResearchTopicFn = Callable[..., Dict]
DiscoverPageImagesFn = Callable[..., Dict]
ImageConfidenceFn = Callable[[str, Dict, Dict], float]

OPENVERSE_SOURCE = "image:openverse"
OPENVERSE_IMAGES_URL = "https://api.openverse.org/v1/images/"
OPENVERSE_PROVIDER_NOTICE = (
    "Made using Openverse. Argus is not endorsed or certified by Openverse."
)
OPENVERSE_LICENSE_NOTICE = (
    "Openverse aggregates third-party metadata; independently verify usage rights "
    "and attribution requirements."
)


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


def _text(value: Any) -> str:
    return clean_text(str(value)) if value is not None else ""


def _http_url(value: Any) -> str:
    url = _text(value)
    return url if is_http_url(url) else ""


def _openverse_rate_limit(headers: Any) -> Dict[str, str]:
    if not headers:
        return {}
    header_map = {
        "anonymous_burst_limit": "x-ratelimit-limit-anon_burst",
        "anonymous_burst_remaining": "x-ratelimit-available-anon_burst",
        "anonymous_sustained_limit": "x-ratelimit-limit-anon_sustained",
        "anonymous_sustained_remaining": "x-ratelimit-available-anon_sustained",
        "retry_after": "retry-after",
    }
    return {
        name: str(headers.get(header_name))
        for name, header_name in header_map.items()
        if headers.get(header_name) is not None
    }


def _normalize_openverse_image(query: str, item: Any, rank: int) -> Optional[Dict]:
    if not isinstance(item, dict) or item.get("mature") is True:
        return None

    image_url = _http_url(item.get("url"))
    if not image_url:
        return None

    title = _text(item.get("title"))
    landing_url = _http_url(item.get("foreign_landing_url"))
    detail_url = _http_url(item.get("detail_url"))
    attribution = _text(item.get("attribution"))
    return {
        "query": query,
        "image_url": image_url,
        "thumbnail_url": _http_url(item.get("thumbnail")),
        "alt": title,
        "width": item.get("width") or "",
        "height": item.get("height") or "",
        "source": OPENVERSE_SOURCE,
        "source_page_url": landing_url or detail_url,
        "source_page_title": title,
        "source_page_snippet": attribution,
        "confidence": None,
        "rank": rank,
        "creator": _text(item.get("creator")),
        "creator_url": _http_url(item.get("creator_url")),
        "provider": _text(item.get("provider")),
        "license": _text(item.get("license")),
        "license_version": _text(item.get("license_version")),
        "license_url": _http_url(item.get("license_url")),
        "attribution": attribution,
        "mature": False,
        "license_verification_required": True,
    }


def search_openverse_images(query: str, limit: int, timeout: int) -> Dict:
    """Search Openverse anonymously and normalize its image metadata."""
    session = create_research_session()
    try:
        response = session.get(
            OPENVERSE_IMAGES_URL,
            params={"q": query, "page_size": limit, "mature": "false"},
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
    except requests.Timeout:
        return _err("Openverse request timed out", code="TIMEOUT")
    except requests.RequestException as exc:
        return _err(f"Openverse request failed: {exc}", code="NETWORK_ERROR")

    rate_limit = _openverse_rate_limit(response.headers)
    if response.status_code == 429:
        return _err(
            "Openverse anonymous rate limit exceeded",
            code="RATE_LIMITED",
            rate_limit=rate_limit,
        )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        return _err(
            f"Openverse returned HTTP {response.status_code}",
            code="HTTP_ERROR",
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError:
        return _err("Openverse returned invalid JSON", code="INVALID_PROVIDER_RESPONSE")
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return _err(
            "Openverse response is missing a results list",
            code="INVALID_PROVIDER_RESPONSE",
        )

    images = []
    for rank, item in enumerate(payload["results"], start=1):
        normalized = _normalize_openverse_image(query, item, rank)
        if normalized:
            images.append(normalized)

    return _ok(
        {
            "images": images,
            "provider_notice": OPENVERSE_PROVIDER_NOTICE,
            "license_notice": OPENVERSE_LICENSE_NOTICE,
            "rate_limit": rate_limit,
        },
        count=len(images),
        reported_result_count=payload.get("result_count"),
    )


def _compact_source_result(result: Dict) -> Dict:
    if not result.get("success"):
        return result
    source_data = dict(result.get("data") or {})
    source_data.pop("images", None)
    return {**result, "data": source_data}


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
    Discover images through Openverse and optional topic-page extraction.

    ``image:openverse`` is a direct, anonymous image source. Other source names
    continue through topic search and preserve source page context.
    """
    query = clean_text(query)
    if not query:
        return _err("query cannot be empty", code="INVALID_QUERY")

    limit = _safe_int(limit, 5, 1, 20)
    images_per_page = _safe_int(images_per_page, 5, 1, 30)
    timeout = _safe_int(timeout, 20, 3, 90)
    selected_sources = sources or [OPENVERSE_SOURCE]
    page_sources = [source for source in selected_sources if source != OPENVERSE_SOURCE]
    source_results = {}
    images = []
    seen_images = set()

    if OPENVERSE_SOURCE in selected_sources:
        openverse_result = search_openverse_images(query=query, limit=limit, timeout=timeout)
        source_results[OPENVERSE_SOURCE] = _compact_source_result(openverse_result)
        if openverse_result.get("success"):
            for image in (openverse_result.get("data") or {}).get("images") or []:
                image_url = image.get("image_url")
                if not image_url or image_url in seen_images:
                    continue
                seen_images.add(image_url)
                images.append(image)

    topic_data = {}
    if page_sources:
        topic_result = research_topic(query=query, sources=page_sources, limit=limit)
        if not topic_result.get("success"):
            return topic_result
        topic_data = topic_result.get("data") or {}
        source_results.update(topic_data.get("sources") or {})

    merged_items = topic_data.get("merged") or []
    candidate_pages = page_candidates(page_candidate_items(topic_data, merged_items), limit)
    errors_by_source = source_errors(source_results)
    page_results = []
    page_images = []

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
            page_images.append(
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

    page_images.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    images.extend(page_images)
    return _ok(
        {
            "query": query,
            "sources": source_results,
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
