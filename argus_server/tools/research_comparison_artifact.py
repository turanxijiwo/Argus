"""Safe loading and indexing for saved research comparison artifacts."""

import json
import os
import re
from typing import Any, Dict, Tuple

from .research_io import resolve_project_path


LOCATOR_PATTERN = re.compile(r"^(S[1-9]\d*):L[1-9]\d*$")
SOURCE_ID_PATTERN = re.compile(r"^S[1-9]\d*$")
SourceCache = Dict[str, Tuple[str, Dict]]


def load_comparison_artifact(path: str, project_root: str) -> Dict:
    resolved = resolve_project_path(path, project_root)
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


def load_comparison_source(
    source: Dict,
    project_root: str,
    source_cache: SourceCache,
) -> Dict:
    source_id = source["source_id"]
    artifact_path = source.get("artifact_path")
    resolved = resolve_project_path(artifact_path, project_root)
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
            os.path.relpath(resolved, project_root),
            payload_result["data"],
        )
    return _ok(source_cache[resolved])


def index_comparison_sources(comparison: Dict) -> Dict:
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
        if not SOURCE_ID_PATTERN.fullmatch(source_id) or source_id in source_ids:
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
        "Comparison artifact contains invalid source or locator metadata",
        "INVALID_COMPARISON_ARTIFACT",
        source_index=source_index,
        reason=reason,
        **extra,
    )


def _ok(data: Any) -> Dict:
    return {"success": True, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
