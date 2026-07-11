"""Bounded evidence replay for locators in saved comparison artifacts."""

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .research_io import resolve_project_path
from .research_locator_evidence import MAX_EXCERPT_WORDS, resolve_locator_evidence


MAX_LOCATOR_REQUESTS = 10
MAX_EXCERPT_CHARS = 240
LOCATOR_PATTERN = re.compile(r"^(S[1-9]\d*):L[1-9]\d*$")


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

        comparison_result = self._load_comparison(comparison_artifact_path)
        if not comparison_result.get("success"):
            return comparison_result
        comparison_path, comparison = comparison_result["data"]

        index_result = _index_comparison_sources(comparison)
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

        source_cache: Dict[str, Tuple[str, Dict]] = {}
        evidence = []
        for locator_id in requested_locator_ids:
            source, locator = locator_index[locator_id]
            source_result = self._load_source(source, source_cache)
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

    def _load_comparison(self, path: str) -> Dict:
        resolved = resolve_project_path(path, self.project_root)
        if not resolved:
            return _err(
                "comparison_artifact_path must point inside the Argus project",
                "UNSAFE_COMPARISON_ARTIFACT_PATH",
            )
        payload_result = _read_json_object(
            resolved,
            "Failed to read comparison artifact",
            "COMPARISON_ARTIFACT_READ_ERROR",
        )
        if not payload_result.get("success"):
            return payload_result
        return _ok((resolved, payload_result["data"]))

    def _load_source(
        self,
        source: Dict,
        source_cache: Dict[str, Tuple[str, Dict]],
    ) -> Dict:
        source_id = source["source_id"]
        artifact_path = source.get("artifact_path")
        resolved = resolve_project_path(artifact_path, self.project_root)
        if not resolved:
            return _err(
                "Source artifact path must point inside the Argus project",
                "UNSAFE_SOURCE_ARTIFACT_PATH",
                source_id=source_id,
            )
        if resolved not in source_cache:
            payload_result = _read_json_object(
                resolved,
                "Failed to read source artifact",
                "SOURCE_ARTIFACT_READ_ERROR",
                source_id=source_id,
            )
            if not payload_result.get("success"):
                return payload_result
            source_cache[resolved] = (
                os.path.relpath(resolved, self.project_root), payload_result["data"]
            )
        return _ok(source_cache[resolved])


def _index_comparison_sources(comparison: Dict) -> Dict:
    sources = comparison.get("sources")
    if not isinstance(sources, list) or not sources:
        return _err(
            "Comparison artifact must contain a non-empty sources list",
            "INVALID_COMPARISON_ARTIFACT",
        )

    source_ids = set()
    locator_index = {}
    for source_index, source in enumerate(sources):
        if not isinstance(source, dict):
            return _invalid_comparison(source_index, "source_not_object")
        source_id = str(source.get("source_id") or "").strip()
        locators = source.get("locators")
        if not re.fullmatch(r"S[1-9]\d*", source_id) or source_id in source_ids:
            return _invalid_comparison(source_index, "invalid_or_duplicate_source_id")
        if not isinstance(source.get("artifact_path"), str) or not source["artifact_path"].strip():
            return _invalid_comparison(source_index, "invalid_source_artifact_path")
        if not isinstance(locators, list):
            return _invalid_comparison(source_index, "locators_not_list")
        source_ids.add(source_id)
        for locator_index_in_source, locator in enumerate(locators):
            if not isinstance(locator, dict):
                return _invalid_comparison(
                    source_index,
                    "locator_not_object",
                    locator_index=locator_index_in_source,
                )
            locator_id = str(locator.get("locator_id") or "").strip()
            match = LOCATOR_PATTERN.fullmatch(locator_id)
            if not match or match.group(1) != source_id or locator_id in locator_index:
                return _invalid_comparison(
                    source_index,
                    "invalid_duplicate_or_mismatched_locator_id",
                    locator_index=locator_index_in_source,
                )
            locator_index[locator_id] = (source, locator)
    return _ok(locator_index)


def _normalize_locator_ids(locator_ids: Iterable[str]) -> List[str]:
    if isinstance(locator_ids, str):
        locator_ids = [locator_ids]
    return [str(locator_id).strip() for locator_id in (locator_ids or []) if str(locator_id).strip()]


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _read_json_object(path: str, message: str, code: str, **extra: Any) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _err(message, code, **extra)
    if not isinstance(payload, dict):
        return _err(message, code, **extra)
    return _ok(payload)


def _invalid_comparison(source_index: int, reason: str, **extra: Any) -> Dict:
    return _err(
        "Comparison artifact contains invalid source or locator metadata", "INVALID_COMPARISON_ARTIFACT",
        source_index=source_index, reason=reason, **extra,
    )


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
