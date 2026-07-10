"""Compact server-side review for one saved Research Toolkit artifact."""

import json
import os
from typing import Any, Dict, List, Optional


MIN_BRIEF_CHARS = 200
MIN_EVIDENCE_TEXT_CHARS = 500


def review_research_artifact(path: str, project_root: str) -> Dict[str, Any]:
    resolved = _resolve_project_path(path, project_root)
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
    brief_chars = len((payload.get("brief") or {}).get("content") or "")
    evidence_chars = sum(len(document.get("text") or "") for document in successful)
    warnings = _warnings(successful, failed, source_errors, brief_chars, evidence_chars)
    score = _score(successful, failed, source_errors, brief_chars, evidence_chars, payload)
    return {
        "success": True,
        "summary": {"quality_status": _status(score, warnings), "score": score},
        "data": {
            "path": _relative_path(resolved, project_root),
            "query": payload.get("query"),
            "quality_status": _status(score, warnings),
            "score": score,
            "warnings": warnings,
            "counts": {
                "documents": len(documents),
                "successful_documents": len(successful),
                "failed_documents": len(failed),
                "images": len(payload.get("images") or []),
                "source_errors": len(source_errors),
                "brief_chars": brief_chars,
                "evidence_text_chars": evidence_chars,
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


def _resolve_project_path(path: str, project_root: str) -> Optional[str]:
    if not path:
        return None
    absolute = os.path.abspath(path if os.path.isabs(path) else os.path.join(project_root, path))
    try:
        if os.path.commonpath([os.path.abspath(project_root), absolute]) != os.path.abspath(project_root):
            return None
    except ValueError:
        return None
    return absolute


def _relative_path(path: str, project_root: str) -> str:
    return os.path.relpath(path, os.path.abspath(project_root))


def _err(message: str, code: str) -> Dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}}
