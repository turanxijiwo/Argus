"""Compact handoff summaries for Research Toolkit workflow outputs."""

import os
from typing import Any, Dict, Iterable, List, Optional


BATCH_HANDOFF_SCHEMA = "argus.research.batch.handoff.v1"


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


def _ready(runs: List[Dict[str, Any]], report_artifact: Dict[str, Any], status_counts: Dict[str, Any]) -> bool:
    return (
        bool(runs)
        and all(run.get("success") for run in runs)
        and bool(report_artifact.get("success"))
        and not status_counts.get("unreadable")
        and not status_counts.get("needs_attention")
    )
