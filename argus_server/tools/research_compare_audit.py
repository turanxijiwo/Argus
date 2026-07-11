"""Compact integrity audits for saved research comparison artifacts."""

import os
from typing import Any, Dict, List, Optional

from .research_comparison_artifact import (
    SourceCache,
    index_comparison_sources,
    load_comparison_artifact,
    load_comparison_source,
)
from .research_locator_evidence import validate_locator_evidence


COMPARISON_AUDIT_SCHEMA = "argus.research.comparison-audit.v1"
CLAIM_CATEGORIES = ("agreements", "differences", "evidence")


class ResearchComparisonAuditTools:
    """Audit every locator used by a comparison without replaying evidence text."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = os.path.realpath(os.path.abspath(project_root or os.getcwd()))

    def research_audit_comparison(self, comparison_artifact_path: str) -> Dict:
        comparison_result = load_comparison_artifact(
            comparison_artifact_path,
            self.project_root,
        )
        if not comparison_result.get("success"):
            return comparison_result
        comparison_path, comparison = comparison_result["data"]

        index_result = index_comparison_sources(comparison)
        if not index_result.get("success"):
            return index_result
        locator_index = index_result["data"]

        references_result = _used_locator_references(comparison)
        if not references_result.get("success"):
            return references_result
        claim_count, locator_ids = references_result["data"]

        source_cache: SourceCache = {}
        source_failures: Dict[str, Dict] = {}
        source_stats: Dict[str, Dict] = {}
        issues: List[Dict] = []
        verified_count = 0
        unverified_count = 0
        failed_count = 0

        for locator_id in locator_ids:
            indexed = locator_index.get(locator_id)
            if not indexed:
                failed_count += 1
                issues.append(
                    {
                        "code": "UNKNOWN_LOCATOR_REFERENCE",
                        "locator_id": locator_id,
                        "reason": "not_registered_in_comparison",
                    }
                )
                continue

            source, locator = indexed
            source_id = source["source_id"]
            source_stat = source_stats.setdefault(source_id, _source_stat(source))
            source_stat["used_locator_count"] += 1

            source_result = source_failures.get(source_id)
            if source_result is None:
                source_result = load_comparison_source(
                    source,
                    self.project_root,
                    source_cache,
                )
                if not source_result.get("success"):
                    source_failures[source_id] = source_result
            if not source_result.get("success"):
                failed_count += 1
                source_stat["failed_locator_count"] += 1
                issues.append(_compact_issue(source_result["error"], locator_id))
                continue

            source_path, source_payload = source_result["data"]
            source_stat["artifact_path"] = source_path
            validation_result = validate_locator_evidence(
                source=source,
                source_path=source_path,
                source_payload=source_payload,
                locator=locator,
            )
            if not validation_result.get("success"):
                failed_count += 1
                source_stat["failed_locator_count"] += 1
                issues.append(_compact_issue(validation_result["error"], locator_id))
                continue

            integrity_status = validation_result["data"]["integrity"]["status"]
            if integrity_status == "verified":
                verified_count += 1
                source_stat["verified_locator_count"] += 1
            else:
                unverified_count += 1
                source_stat["unverified_locator_count"] += 1

        sources = list(source_stats.values())
        for source in sources:
            source["status"] = _audit_status(
                source["verified_locator_count"],
                source["unverified_locator_count"],
                source["failed_locator_count"],
            )
        status = _audit_status(verified_count, unverified_count, failed_count)
        relative_comparison_path = os.path.relpath(comparison_path, self.project_root)
        audit = {
            "schema": COMPARISON_AUDIT_SCHEMA,
            "comparison_artifact_path": relative_comparison_path,
            "status": status,
            "source_count": len(comparison.get("sources") or []),
            "audited_source_count": len(sources),
            "claim_count": claim_count,
            "used_locator_count": len(locator_ids),
            "verified_locator_count": verified_count,
            "unverified_locator_count": unverified_count,
            "failed_locator_count": failed_count,
            "sources": sources,
            "issues": issues,
        }
        return _ok(
            audit,
            status=status,
            source_count=audit["source_count"],
            audited_source_count=audit["audited_source_count"],
            claim_count=claim_count,
            used_locator_count=len(locator_ids),
            verified_locator_count=verified_count,
            unverified_locator_count=unverified_count,
            failed_locator_count=failed_count,
            issue_count=len(issues),
        )


def _used_locator_references(comparison: Dict) -> Dict:
    comparison_payload = comparison.get("comparison")
    if not isinstance(comparison_payload, dict):
        return _invalid_comparison("comparison_not_object")

    claim_count = 0
    locator_ids = []
    for category in CLAIM_CATEGORIES:
        claims = comparison_payload.get(category, [])
        if not isinstance(claims, list):
            return _invalid_comparison("claims_not_list", category=category)
        for claim_index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                return _invalid_comparison(
                    "claim_not_object",
                    category=category,
                    claim_index=claim_index,
                )
            claim_count += 1
            locators = claim.get("locators")
            if not isinstance(locators, list):
                return _invalid_comparison(
                    "claim_locators_not_list",
                    category=category,
                    claim_index=claim_index,
                )
            for locator_index, locator_id in enumerate(locators):
                normalized = str(locator_id or "").strip().strip("[]`").upper()
                if not normalized:
                    return _invalid_comparison(
                        "invalid_locator_reference",
                        category=category,
                        claim_index=claim_index,
                        locator_index=locator_index,
                    )
                if normalized not in locator_ids:
                    locator_ids.append(normalized)

    if not locator_ids:
        return _err(
            "Comparison artifact does not contain any used evidence locators",
            "NO_USED_LOCATORS",
        )
    return _ok((claim_count, locator_ids))


def _source_stat(source: Dict) -> Dict:
    return {
        "source_id": source["source_id"],
        "title": source.get("title") or source["source_id"],
        "artifact_path": None,
        "status": "unverified",
        "used_locator_count": 0,
        "verified_locator_count": 0,
        "unverified_locator_count": 0,
        "failed_locator_count": 0,
    }


def _audit_status(verified_count: int, unverified_count: int, failed_count: int) -> str:
    if failed_count:
        return "failed"
    if unverified_count:
        return "unverified"
    return "verified" if verified_count else "unverified"


def _compact_issue(error: Dict, locator_id: str) -> Dict:
    issue = {
        "code": error.get("code") or "LOCATOR_AUDIT_ERROR",
        "locator_id": locator_id,
    }
    for key in ("source_id", "document_index", "reason"):
        if key in error:
            issue[key] = error[key]
    return issue


def _invalid_comparison(reason: str, **extra: Any) -> Dict:
    return _err(
        "Comparison artifact contains invalid claim locator metadata",
        "INVALID_COMPARISON_ARTIFACT",
        reason=reason,
        **extra,
    )


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
