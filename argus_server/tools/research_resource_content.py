"""Public-access selection and document normalization for research resources."""

from typing import Dict, List, Optional


OPEN_ACCESS_STATES = {"open_download", "open_read"}
READABLE_FORMATS = ("pdf", "html", "txt")


def select_readable_resource_url(resource: Dict) -> Optional[Dict]:
    files = resource.get("file_urls") or []
    for selected_format in READABLE_FORMATS:
        for item in files:
            if item.get("format") != selected_format or not item.get("url"):
                continue
            return {
                "url": item["url"],
                "format": selected_format,
                "content_scope": "fulltext_candidate",
            }
    landing_page = resource.get("landing_page_url")
    if landing_page:
        return {
            "url": landing_page,
            "format": "web",
            "content_scope": "resource_page",
            "unsupported_file_formats": sorted(
                {item.get("format") for item in files if item.get("format")}
            ),
        }
    return None


def resource_document(
    query: str,
    resource: Dict,
    selection: Dict,
    read_result: Dict,
    max_chars: int,
) -> Dict:
    document = {
        "query": query,
        "source": ",".join(resource.get("sources") or []),
        "url": selection["url"],
        "title": resource.get("title"),
        "snippet": _resource_description(resource),
        "score": resource.get("relevance_score"),
        "success": bool(read_result.get("success")),
        "error": read_result.get("error"),
        "crawl_attempts": 1,
        "reader": "jina",
    }
    if not read_result.get("success"):
        return document
    content = ((read_result.get("data") or {}).get("content") or "").strip()
    document.update(
        {
            "final_url": selection["url"],
            "status_code": 200,
            "content_type": selection.get("format"),
            "page_title": resource.get("title"),
            "description": _resource_description(resource),
            "text": content[:max_chars],
            "text_truncated": len(content) > max_chars,
            "links": [],
            "images": [],
        }
    )
    return document


def validate_resource_access(resource: Dict, allow_unverified: bool) -> Optional[Dict]:
    access = resource.get("access")
    if access not in OPEN_ACCESS_STATES and access != "unverified":
        return _err(
            "Selected resource is not publicly readable",
            "ACCESS_NOT_OPEN",
            access=access,
        )
    if (
        access == "unverified" or not resource.get("verified_open_access")
    ) and not allow_unverified:
        return _err(
            "Selected resource access has not been verified",
            "UNVERIFIED_ACCESS",
            access=access,
            suggestion="Set allow_unverified=true only for a public URL you trust",
        )
    return None


def selected_sources(resource: Dict, errors: List[Dict]) -> Dict[str, Dict]:
    failed_sources = {error.get("source") for error in errors}
    return {
        source: {"success": source not in failed_sources}
        for source in resource.get("sources") or []
    }


def _resource_description(resource: Dict) -> Optional[str]:
    records = (resource.get("metadata") or {}).get("records") or {}
    for record in records.values():
        for key in ("summary", "abstract", "snippet", "description"):
            if record.get(key):
                return str(record[key])
    return None


def _err(message: str, code: str, **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
