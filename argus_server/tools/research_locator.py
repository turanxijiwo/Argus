"""Bounded evidence replay for locators in saved comparison artifacts."""

import os
from typing import Any, Dict, Iterable, List, Optional

from .research_comparison_artifact import (
    SourceCache,
    index_comparison_sources,
    load_comparison_artifact,
    load_comparison_source,
)
from .research_locator_evidence import MAX_EXCERPT_WORDS, resolve_locator_evidence


MAX_LOCATOR_REQUESTS = 10
MAX_EXCERPT_CHARS = 240


class ResearchLocatorTools:
    """Resolve saved comparison locators without replaying full documents."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = os.path.realpath(os.path.abspath(project_root or os.getcwd()))

    def research_resolve_locators(
        self,
        comparison_artifact_path: str,
        locator_ids: Iterable[str],
        max_chars: int = MAX_EXCERPT_CHARS,
    ) -> Dict:
        raw_locator_ids = _normalize_locator_ids(locator_ids)
        if not raw_locator_ids:
            return _err("At least one locator ID is required", "EMPTY_LOCATOR_IDS")
        if len(raw_locator_ids) > MAX_LOCATOR_REQUESTS:
            return _err(
                f"No more than {MAX_LOCATOR_REQUESTS} locator IDs can be resolved",
                "TOO_MANY_LOCATORS",
                max_locators=MAX_LOCATOR_REQUESTS,
            )
        requested_locator_ids = list(dict.fromkeys(raw_locator_ids))
        selected_max_chars = _safe_int(max_chars, MAX_EXCERPT_CHARS, 1, MAX_EXCERPT_CHARS)

        comparison_result = load_comparison_artifact(comparison_artifact_path, self.project_root)
        if not comparison_result.get("success"):
            return comparison_result
        comparison_path, comparison = comparison_result["data"]

        index_result = index_comparison_sources(comparison)
        if not index_result.get("success"):
            return index_result
        locator_index = index_result["data"]
        unknown = [locator_id for locator_id in requested_locator_ids if locator_id not in locator_index]
        if unknown:
            return _err(
                "One or more locator IDs are not present in the comparison artifact",
                "UNKNOWN_LOCATORS",
                locator_ids=unknown,
            )

        source_cache: SourceCache = {}
        evidence = []
        for locator_id in requested_locator_ids:
            source, locator = locator_index[locator_id]
            source_result = load_comparison_source(source, self.project_root, source_cache)
            if not source_result.get("success"):
                source_result["error"]["locator_id"] = locator_id
                return source_result
            source_path, source_payload = source_result["data"]
            evidence_result = resolve_locator_evidence(
                source=source,
                source_path=source_path,
                source_payload=source_payload,
                locator=locator,
                max_chars=selected_max_chars,
            )
            if not evidence_result.get("success"):
                return evidence_result
            evidence.append(evidence_result["data"])

        relative_comparison_path = os.path.relpath(comparison_path, self.project_root)
        integrity_verified_count = sum(
            1 for item in evidence if item["integrity"]["status"] == "verified"
        )
        integrity_unverified_count = len(evidence) - integrity_verified_count
        integrity_status = (
            "verified" if not integrity_unverified_count
            else "partial" if integrity_verified_count
            else "unverified"
        )
        return _ok(
            {
                "comparison_artifact_path": relative_comparison_path,
                "locator_ids": requested_locator_ids,
                "limits": {
                    "max_locators": MAX_LOCATOR_REQUESTS,
                    "max_excerpt_chars": selected_max_chars,
                    "max_excerpt_words": MAX_EXCERPT_WORDS,
                },
                "integrity": {
                    "status": integrity_status,
                    "verified_count": integrity_verified_count,
                    "unverified_count": integrity_unverified_count,
                },
                "evidence": evidence,
            },
            locator_count=len(evidence),
            source_count=len({item["source_id"] for item in evidence}),
            truncated_count=sum(1 for item in evidence if item["excerpt_truncated"]),
            integrity_status=integrity_status,
            integrity_verified_count=integrity_verified_count,
            integrity_unverified_count=integrity_unverified_count,
            max_excerpt_chars=selected_max_chars,
            max_excerpt_words=MAX_EXCERPT_WORDS,
        )

def _normalize_locator_ids(locator_ids: Iterable[str]) -> List[str]:
    if isinstance(locator_ids, str):
        locator_ids = [locator_ids]
    return [str(locator_id).strip() for locator_id in (locator_ids or []) if str(locator_id).strip()]


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
