"""Metadata-only yt-dlp adapter for public media pages."""

import json
import re
import shutil
import subprocess
from typing import Any, Dict, Optional
from urllib.parse import urlparse


SCHEMA = "argus.research.video.metadata.v1"

_TEXT_FIELDS = {
    "id": 256,
    "title": 500,
    "description": 4000,
    "extractor": 100,
    "extractor_key": 100,
    "channel": 500,
    "channel_id": 256,
    "uploader": 500,
    "uploader_id": 256,
    "upload_date": 32,
    "release_date": 32,
    "availability": 64,
    "live_status": 64,
    "license": 500,
    "language": 64,
    "artist": 500,
    "creator": 500,
    "track": 500,
    "album": 500,
    "genre": 200,
}
_NUMBER_FIELDS = {
    "duration": "duration_seconds",
    "timestamp": "timestamp",
    "release_timestamp": "release_timestamp",
    "view_count": "view_count",
    "like_count": "like_count",
    "comment_count": "comment_count",
    "channel_follower_count": "channel_follower_count",
    "age_limit": "age_limit",
    "release_year": "release_year",
}
_PAGE_URL_FIELDS = {
    "channel_url": "channel_url",
    "uploader_url": "uploader_url",
}


def inspect_video_metadata(url: str, timeout: int = 60) -> Dict:
    """Extract a bounded metadata allowlist without downloading media."""
    binary = shutil.which("yt-dlp")
    if not binary:
        return _err(
            "yt-dlp is not installed",
            code="NOT_INSTALLED",
            install_hint="uv tool install yt-dlp",
        )

    target_url = (url or "").strip()
    if not _is_http_url(target_url):
        return _err("url must be a non-empty http/https URL", code="INVALID_URL")

    timeout_seconds = _safe_int(timeout, default=60, minimum=10, maximum=180)
    socket_timeout = min(timeout_seconds, 30)
    command = [
        binary,
        "--ignore-config",
        "--simulate",
        "--dump-single-json",
        "--no-playlist",
        "--playlist-items",
        "1",
        "--no-cookies",
        "--no-cookies-from-browser",
        "--no-cache-dir",
        "--no-remote-components",
        "--no-mark-watched",
        "--xff",
        "never",
        "--no-warnings",
        "--no-progress",
        "--color",
        "never",
        "--socket-timeout",
        str(socket_timeout),
        "--retries",
        "2",
        "--extractor-retries",
        "2",
        target_url,
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _err(
            "yt-dlp metadata extraction timed out",
            code="TIMEOUT",
            timeout=timeout_seconds,
        )
    except Exception as ex:
        return _err(
            f"yt-dlp failed to start: {type(ex).__name__}",
            code="EXEC_ERROR",
        )

    if completed.returncode != 0:
        detail = _sanitize_process_text(completed.stderr)
        return _err(
            "yt-dlp could not extract public metadata",
            code="EXTRACTOR_ERROR",
            returncode=completed.returncode,
            **({"detail": detail} if detail else {}),
        )

    try:
        raw_metadata = json.loads((completed.stdout or "").strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        return _err("yt-dlp returned invalid JSON", code="PARSE_ERROR")

    if not isinstance(raw_metadata, dict):
        return _err("yt-dlp returned an unexpected response", code="INVALID_RESPONSE")
    if raw_metadata.get("_type") in {"playlist", "multi_video"} or isinstance(
        raw_metadata.get("entries"), list
    ):
        return _err("playlist metadata is not supported", code="UNSUPPORTED_TARGET")

    metadata = _normalize_metadata(raw_metadata)
    if not metadata.get("id") or not metadata.get("title"):
        return _err("yt-dlp response is missing id or title", code="INVALID_RESPONSE")

    return _ok(
        {
            "schema": SCHEMA,
            "metadata": metadata,
            "safety": {
                "mode": "metadata_only",
                "downloaded_media": False,
                "wrote_files": False,
                "cookies_used": False,
                "browser_cookies_used": False,
                "cache_used": False,
                "remote_components_allowed": False,
                "playlists_allowed": False,
                "direct_media_urls_included": False,
            },
        },
        mode="metadata_only",
        extractor=metadata.get("extractor"),
        metadata_field_count=len(metadata),
    )


def _normalize_metadata(raw_metadata: Dict[str, Any]) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    for field, max_chars in _TEXT_FIELDS.items():
        value = _bounded_text(raw_metadata.get(field), max_chars)
        if value is not None:
            metadata[field] = value

    for source_field, output_field in _NUMBER_FIELDS.items():
        value = raw_metadata.get(source_field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metadata[output_field] = value

    for field in ("is_live", "was_live"):
        value = raw_metadata.get(field)
        if isinstance(value, bool):
            metadata[field] = value

    source_page_url = _page_url(raw_metadata.get("webpage_url"))
    if source_page_url and source_page_url != raw_metadata.get("url"):
        metadata["source_page_url"] = source_page_url

    for source_field, output_field in _PAGE_URL_FIELDS.items():
        value = _page_url(raw_metadata.get(source_field))
        if value:
            metadata[output_field] = value

    for field in ("categories", "tags"):
        values = _bounded_text_list(raw_metadata.get(field), limit=50, max_chars=200)
        if values:
            metadata[field] = values
    return metadata


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _page_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    clean_value = value.strip()
    if not _is_http_url(clean_value):
        return None
    return clean_value[:2048]


def _bounded_text(value: Any, max_chars: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    clean_value = value.strip()
    return clean_value[:max_chars] if clean_value else None


def _bounded_text_list(value: Any, limit: int, max_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value[:limit]:
        clean_item = _bounded_text(item, max_chars)
        if clean_item:
            normalized.append(clean_item)
    return normalized


def _sanitize_process_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    sanitized = re.sub(r"https?://\S+", "[url]", value)
    sanitized = sanitized.replace("\x1b", "")
    return sanitized.strip()[-2000:]


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
