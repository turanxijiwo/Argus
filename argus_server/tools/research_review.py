"""Compact server-side review for one saved Research Toolkit artifact."""

import json
import os
from typing import Any, Dict, List, Optional

from .research_handoff import summarize_image_candidates
from .research_io import resolve_project_path


MIN_BRIEF_CHARS = 200
MIN_EVIDENCE_TEXT_CHARS = 500
REVIEW_HANDOFF_SCHEMA = "argus.research.review.handoff.v1"


def review_research_artifact(
    path: Optional[str],
    project_root: str,
    handoff: Optional[Dict[str, Any]] = None,
    artifact_index: int = 0,
) -> Dict[str, Any]:
    if not path and handoff:
        path = _handoff_artifact_path(handoff, artifact_index)
        if not path:
            return _err("handoff does not contain a selected artifact path", "INVALID_HANDOFF")
    resolved = resolve_project_path(path, project_root)
    if not resolved:
        return _err("artifact_path must point inside the Argus project", "UNSAFE_ARTIFACT_PATH")
    try:
        with open(resolved, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as ex:
        return _err(f"Failed to read research artifact: {ex}", "ARTIFACT_READ_ERROR")
    if not isinstance(payload, dict):
        return _err("research artifact must contain a JSON object", "INVALID_ARTIFACT")

    documents = payload.get("documents") or []
    successful = [document for document in documents if document.get("success")]
    failed = [document for document in documents if not document.get("success")]
    source_errors = payload.get("source_errors") or []
    image_summary = summarize_image_candidates(payload.get("images") or [])
    brief_chars = len((payload.get("brief") or {}).get("content") or "")
    evidence_chars = sum(len(document.get("text") or "") for document in successful)
    warnings = _warnings(successful, failed, source_errors, brief_chars, evidence_chars)
    score = _score(successful, failed, source_errors, brief_chars, evidence_chars, payload)
    quality_status = _status(score, warnings)
    relative_path = _relative_path(resolved, project_root)
    return {
        "success": True,
        "summary": {
            "quality_status": quality_status,
            "score": score,
            "license_warning_count": len(image_summary["license_warnings"]),
        },
        "data": {
            "path": relative_path,
            "query": payload.get("query"),
            "quality_status": quality_status,
            "score": score,
            "warnings": warnings,
            "license_warnings": image_summary["license_warnings"],
            "counts": {
                "documents": len(documents),
                "successful_documents": len(successful),
                "failed_documents": len(failed),
                "images": image_summary["images"],
                "openverse_images": image_summary["openverse_images"],
                "page_images": image_summary["page_images"],
                "openverse_license_complete": image_summary["openverse_license_complete"],
                "license_verification_required_images": image_summary["license_verification_required_images"],
                "source_errors": len(source_errors),
                "brief_chars": brief_chars,
                "evidence_text_chars": evidence_chars,
            },
            "handoff": {
                "schema": REVIEW_HANDOFF_SCHEMA,
                "ready": quality_status == "ready",
                "artifact_path": relative_path,
                "quality_status": quality_status,
                "score": score,
                "warnings": warnings,
                "openverse_image_count": image_summary["openverse_images"],
                "page_image_count": image_summary["page_images"],
                "openverse_license_complete_count": image_summary["openverse_license_complete"],
                "license_verification_required_count": image_summary["license_verification_required_images"],
                "license_warnings": image_summary["license_warnings"],
            },
        },
    }


def _warnings(successful: List[Dict], failed: List[Dict], source_errors: List[Dict], brief_chars: int, evidence_chars: int) -> List[str]:
    warnings = []
    if not successful:
        warnings.append("no_successful_documents")
    if failed:
        warnings.append("page_errors_present")
    if source_errors:
        warnings.append("source_errors_present")
    if not brief_chars:
        warnings.append("missing_brief")
    elif brief_chars < MIN_BRIEF_CHARS:
        warnings.append("short_brief")
    if successful and evidence_chars < MIN_EVIDENCE_TEXT_CHARS:
        warnings.append("low_evidence_text")
    return warnings


def _score(successful: List[Dict], failed: List[Dict], source_errors: List[Dict], brief_chars: int, evidence_chars: int, payload: Dict) -> int:
    score = 35 if successful else 0
    score += 15 if not failed else 0
    score += 15 if not source_errors else 0
    score += 15 if brief_chars >= MIN_BRIEF_CHARS else 0
    score += 15 if evidence_chars >= MIN_EVIDENCE_TEXT_CHARS else 0
    score += 5 if payload.get("sources") else 0
    return min(score, 100)


def _status(score: int, warnings: List[str]) -> str:
    if score >= 80 and not warnings:
        return "ready"
    if score >= 40:
        return "partial"
    return "needs_attention"


def _relative_path(path: str, project_root: str) -> str:
    return os.path.relpath(path, os.path.realpath(os.path.abspath(project_root)))


def _handoff_artifact_path(handoff: Dict[str, Any], artifact_index: int) -> Optional[str]:
    if handoff.get("artifact_path"):
        return handoff["artifact_path"]
    artifact_paths = handoff.get("artifact_paths") or []
    try:
        index = int(artifact_index)
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(artifact_paths):
        return None
    return artifact_paths[index]


def _err(message: str, code: str) -> Dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}}
