"""Metadata-only Openverse audio search for Argus."""

from typing import Any, Dict, Optional

import requests

from .research_images import (
    OPENVERSE_LICENSE_NOTICE,
    OPENVERSE_PROVIDER_NOTICE,
    _openverse_rate_limit,
)
from .research_runtime import create_research_session
from .research_web import clean_text, is_http_url


OPENVERSE_AUDIO_SOURCE = "audio:openverse"
OPENVERSE_AUDIO_URL = "https://api.openverse.org/v1/audio/"


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_TOOLKIT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
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


def _non_negative_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return value


def _normalize_openverse_audio(query: str, item: Any, rank: int) -> Optional[Dict]:
    if not isinstance(item, dict) or item.get("mature") is True:
        return None

    audio_url = _http_url(item.get("url"))
    if not audio_url:
        return None

    title = _text(item.get("title"))
    landing_url = _http_url(item.get("foreign_landing_url"))
    detail_url = _http_url(item.get("detail_url"))
    attribution = _text(item.get("attribution"))
    return {
        "query": query,
        "title": title,
        "audio_url": audio_url,
        "source": OPENVERSE_AUDIO_SOURCE,
        "source_page_url": landing_url or detail_url,
        "source_page_title": title,
        "source_page_snippet": attribution,
        "rank": rank,
        "creator": _text(item.get("creator")),
        "creator_url": _http_url(item.get("creator_url")),
        "provider": _text(item.get("provider")),
        "license": _text(item.get("license")),
        "license_version": _text(item.get("license_version")),
        "license_url": _http_url(item.get("license_url")),
        "attribution": attribution,
        "duration_ms": _non_negative_number(item.get("duration")),
        "filetype": _text(item.get("filetype")),
        "filesize": _non_negative_number(item.get("filesize")),
        "mature": False,
        "license_verification_required": True,
    }


def search_openverse_audio(query: str, limit: int = 5, timeout: int = 20) -> Dict:
    """Search Openverse anonymously and return metadata without fetching audio."""
    query = clean_text(query)
    if not query:
        return _err("query cannot be empty", code="INVALID_QUERY")

    limit = _safe_int(limit, 5, 1, 20)
    timeout = _safe_int(timeout, 20, 3, 90)
    session = create_research_session()
    try:
        response = session.get(
            OPENVERSE_AUDIO_URL,
            params={"q": query, "page_size": limit, "mature": "false"},
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
    except requests.Timeout:
        return _err("Openverse audio request timed out", code="TIMEOUT")
    except requests.RequestException as exc:
        return _err(f"Openverse audio request failed: {exc}", code="NETWORK_ERROR")

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
            f"Openverse audio returned HTTP {response.status_code}",
            code="HTTP_ERROR",
            status_code=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError:
        return _err(
            "Openverse audio returned invalid JSON",
            code="INVALID_PROVIDER_RESPONSE",
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return _err(
            "Openverse audio response is missing a results list",
            code="INVALID_PROVIDER_RESPONSE",
        )

    audio_items = []
    seen_urls = set()
    for rank, item in enumerate(payload["results"], start=1):
        normalized = _normalize_openverse_audio(query, item, rank)
        if not normalized or normalized["audio_url"] in seen_urls:
            continue
        seen_urls.add(normalized["audio_url"])
        audio_items.append(normalized)

    return _ok(
        {
            "audio": audio_items,
            "provider_notice": OPENVERSE_PROVIDER_NOTICE,
            "license_notice": OPENVERSE_LICENSE_NOTICE,
            "rate_limit": rate_limit,
        },
        count=len(audio_items),
        reported_result_count=payload.get("result_count"),
    )
