"""Compact handoff summaries for Research Toolkit workflow outputs."""

import os
from typing import Any, Dict, Iterable, List, Optional

from .research_io import resolve_project_path


BATCH_HANDOFF_SCHEMA = "argus.research.batch.handoff.v1"
COMPARISON_HANDOFF_SCHEMA = "argus.research.comparison.handoff.v1"
WORKFLOW_HANDOFF_SCHEMA = "argus.research.workflow.handoff.v1"


def build_workflow_handoff(
    workflow: Dict[str, Any],
    project_root: str,
    output_dir: str = "",
    entrypoint: str = "mcp",
) -> Dict[str, Any]:
    documents = workflow.get("documents") or []
    successful_documents = sum(1 for document in documents if document.get("success"))
    crawl_error_count = sum(1 for document in documents if not document.get("success"))
    source_errors = workflow.get("source_errors") or {}
    artifact_path = _project_relative_path(
        (workflow.get("artifact") or {}).get("path"), project_root
    )
    brief_path = _project_relative_path(
        ((workflow.get("brief") or {}).get("artifact") or {}).get("path"), project_root
    )
    ready = bool(
        artifact_path
        and documents
        and successful_documents
        and not source_errors
        and not crawl_error_count
    )
    status = "ready" if ready else "partial" if successful_documents else "needs_attention"
    return {
        "schema": WORKFLOW_HANDOFF_SCHEMA,
        "entrypoint": entrypoint,
        "ready": ready,
        "status": status,
        "query": workflow.get("query", ""),
        "artifact_path": artifact_path,
        "brief_path": brief_path,
        "document_count": len(documents),
        "successful_document_count": successful_documents,
        "crawl_error_count": crawl_error_count,
        "source_error_count": len(source_errors),
        "image_count": len(workflow.get("images") or []),
        "output_dir": _relative_hint(output_dir),
    }


def build_batch_handoff(
    runs: Iterable[Dict[str, Any]],
    artifact_paths: Optional[Iterable[str]] = None,
    review: Optional[Dict[str, Any]] = None,
    report_artifact: Optional[Dict[str, Any]] = None,
    query_count: Optional[int] = None,
    output_dir: str = "",
    review_report: str = "",
    entrypoint: str = "mcp",
    exit_code: Optional[int] = None,
    ready: Optional[bool] = None,
) -> Dict[str, Any]:
    selected_runs = list(runs or [])
    selected_artifact_paths = list(artifact_paths or _run_paths(selected_runs, "artifact_path"))
    selected_brief_paths = list(_run_paths(selected_runs, "brief_path"))
    selected_review = review or {}
    selected_report_artifact = report_artifact or selected_review.get("report_artifact") or {}
    status_counts = selected_review.get("status_counts") or {}
    report_path = _report_path(selected_report_artifact) or _relative_hint(review_report)
    return {
        "schema": BATCH_HANDOFF_SCHEMA,
        "entrypoint": entrypoint,
        "ready": _ready(selected_runs, selected_report_artifact, status_counts) if ready is None else bool(ready),
        "query_count": query_count if query_count is not None else len(selected_runs),
        "successful_workflow_count": sum(1 for run in selected_runs if run.get("success")),
        "failed_workflow_count": sum(1 for run in selected_runs if not run.get("success")),
        "artifact_count": len(selected_artifact_paths),
        "artifact_paths": selected_artifact_paths,
        "brief_paths": selected_brief_paths,
        "review_report": report_path,
        "status_counts": status_counts,
        "average_score": selected_review.get("average_score", 0),
        "output_dir": output_dir,
        "exit_code": exit_code,
    }


def build_comparison_handoff(
    report: Dict[str, Any],
    project_root: str,
    output_dir: str = "",
    entrypoint: str = "mcp",
) -> Dict[str, Any]:
    comparison = report.get("comparison") or {}
    artifact_path = _project_relative_path(
        (report.get("artifact") or {}).get("path"), project_root
    )
    brief_path = _project_relative_path(
        ((report.get("brief") or {}).get("artifact") or {}).get("path"), project_root
    )
    citation_artifacts = report.get("citation_artifacts") or {}
    csl_json_path = _project_relative_path(
        (citation_artifacts.get("csl_json") or {}).get("path"), project_root
    )
    ris_path = _project_relative_path(
        (citation_artifacts.get("ris") or {}).get("path"), project_root
    )
    source_count = len(report.get("sources") or [])
    citations_valid = bool(
        (comparison.get("citation_validation") or {}).get("valid")
    )
    ready = bool(
        artifact_path
        and source_count >= 2
        and comparison.get("claim_count")
        and citations_valid
    )
    return {
        "schema": COMPARISON_HANDOFF_SCHEMA,
        "entrypoint": entrypoint,
        "ready": ready,
        "status": "ready" if ready else "partial" if comparison else "needs_attention",
        "query": report.get("query", ""),
        "artifact_path": artifact_path,
        "brief_path": brief_path,
        "csl_json_path": csl_json_path,
        "ris_path": ris_path,
        "source_count": source_count,
        "claim_count": comparison.get("claim_count") or 0,
        "citation_count": comparison.get("citation_count") or 0,
        "locator_count": comparison.get("locator_count") or 0,
        "citations_valid": citations_valid,
        "locators_valid": citations_valid,
        "output_dir": _relative_hint(output_dir),
    }


def _run_paths(runs: List[Dict[str, Any]], key: str) -> List[str]:
    return [run[key] for run in runs if run.get(key)]


def _report_path(report_artifact: Dict[str, Any]) -> Optional[str]:
    if not report_artifact:
        return None
    data = report_artifact.get("data") or {}
    summary = report_artifact.get("summary") or {}
    return data.get("path") or report_artifact.get("path") or summary.get("path")


def _relative_hint(path: str) -> Optional[str]:
    if not path or os.path.isabs(path):
        return None
    return path


def _project_relative_path(path: Optional[str], project_root: str) -> Optional[str]:
    absolute_path = resolve_project_path(path, project_root)
    if not absolute_path:
        return None
    root = os.path.realpath(os.path.abspath(project_root))
    return os.path.relpath(absolute_path, root)


def _ready(runs: List[Dict[str, Any]], report_artifact: Dict[str, Any], status_counts: Dict[str, Any]) -> bool:
    return (
        bool(runs)
        and all(run.get("success") for run in runs)
        and bool(report_artifact.get("success"))
        and not status_counts.get("unreadable")
        and not status_counts.get("needs_attention")
    )
