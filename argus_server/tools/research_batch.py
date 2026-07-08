"""Batch workflow orchestration for saved Argus research artifacts."""

import os
from typing import Any, Callable, Dict, Iterable, List, Optional

from .research_web import clean_text

ResearchWorkflowFn = Callable[..., Dict]

DEFAULT_BATCH_OUTPUT_DIR = "output/research/batch"
DEFAULT_BATCH_REPORT_PATH = "output/research/artifact-reviews/batch-review.md"
MAX_BATCH_QUERIES = 25
MIN_EVIDENCE_TEXT_CHARS = 500


def build_research_batch_workflow(
    queries: Iterable[str],
    sources: Optional[List[str]],
    limit: int,
    timeout: int,
    max_chars_per_page: int,
    images_per_page: int,
    render_js: bool,
    retries: int,
    output_dir: str,
    report_path: str,
    project_root: str,
    research_workflow: ResearchWorkflowFn,
) -> Dict:
    """Run saved research workflows for multiple queries and write a compact report."""
    selected_queries = _normalize_queries(queries)
    if not selected_queries:
        return _err("queries cannot be empty", code="INVALID_QUERIES")
    if len(selected_queries) > MAX_BATCH_QUERIES:
        return _err(
            f"queries cannot contain more than {MAX_BATCH_QUERIES} items",
            code="TOO_MANY_QUERIES",
            max_queries=MAX_BATCH_QUERIES,
        )

    selected_sources = sources or []
    selected_output_dir = output_dir or DEFAULT_BATCH_OUTPUT_DIR
    selected_report_path = report_path or DEFAULT_BATCH_REPORT_PATH
    runs = []
    for query in selected_queries:
        result = research_workflow(
            query=query,
            sources=selected_sources,
            limit=limit,
            timeout=timeout,
            max_chars_per_page=max_chars_per_page,
            images_per_page=images_per_page,
            render_js=render_js,
            retries=retries,
            include_brief=True,
            save=True,
            save_brief=True,
            output_dir=selected_output_dir,
        )
        runs.append(summarize_workflow_result(query, result, project_root))

    review = review_runs(runs)
    markdown = render_batch_report(
        runs=runs,
        review=review,
        sources=selected_sources,
        output_dir=selected_output_dir,
    )
    report_artifact = write_batch_report(markdown, selected_report_path, project_root)
    all_runs_success = all(run.get("success") for run in runs)
    batch_success = all_runs_success and bool(report_artifact.get("success"))
    data = {
        "queries": selected_queries,
        "sources": selected_sources,
        "runs": runs,
        "artifact_paths": [run["artifact_path"] for run in runs if run.get("artifact_path")],
        "review": review,
        "report_artifact": report_artifact,
    }
    response = _ok(
        data,
        query_count=len(selected_queries),
        successful_workflow_count=sum(1 for run in runs if run.get("success")),
        failed_workflow_count=sum(1 for run in runs if not run.get("success")),
        artifact_count=len(data["artifact_paths"]),
        average_score=review.get("average_score", 0),
        status_counts=review.get("status_counts") or {},
        report_written=bool(report_artifact.get("success")),
        output_dir=selected_output_dir,
        review_report=selected_report_path,
    )
    response["success"] = batch_success
    if not batch_success:
        response["error"] = _batch_error(runs, report_artifact)
    return response


def summarize_workflow_result(query: str, result: Dict[str, Any], project_root: str) -> Dict[str, Any]:
    data = result.get("data") or {}
    documents = data.get("documents") or []
    successful_documents = [document for document in documents if document.get("success")]
    failed_documents = [document for document in documents if not document.get("success")]
    source_errors = data.get("source_errors") or []
    brief = data.get("brief") or {}
    brief_content = brief.get("content") or ""
    artifact = data.get("artifact") or {}
    brief_artifact = brief.get("artifact") or {}
    evidence_text_chars = sum(len(document.get("text") or "") for document in successful_documents)
    run = {
        "query": query,
        "success": bool(result.get("success")),
        "artifact_path": _relative_path(artifact.get("path"), project_root),
        "brief_path": _relative_path(brief_artifact.get("path"), project_root),
        "document_count": len(documents),
        "successful_document_count": len(successful_documents),
        "crawl_error_count": len(failed_documents),
        "source_error_count": len(source_errors),
        "image_count": len(data.get("images") or []),
        "brief_included": bool(brief_content),
        "brief_chars": len(brief_content),
        "evidence_text_chars": evidence_text_chars,
        "error": result.get("error") or {},
    }
    run["warnings"] = run_warnings(run)
    run["score"] = run_score(run)
    run["quality_status"] = quality_status(run["score"], run["warnings"])
    return run


def run_warnings(run: Dict[str, Any]) -> List[str]:
    warnings = []
    if not run.get("success"):
        warnings.append("workflow_failed")
    if not run.get("artifact_path"):
        warnings.append("missing_artifact")
    if not run.get("successful_document_count"):
        warnings.append("no_successful_documents")
    if run.get("crawl_error_count"):
        warnings.append("page_errors_present")
    if run.get("source_error_count"):
        warnings.append("source_errors_present")
    if not run.get("brief_included"):
        warnings.append("missing_brief")
    if run.get("successful_document_count") and run.get("evidence_text_chars", 0) < MIN_EVIDENCE_TEXT_CHARS:
        warnings.append("low_evidence_text")
    return warnings


def run_score(run: Dict[str, Any]) -> int:
    score = 0
    if run.get("successful_document_count"):
        score += 35
    if not run.get("crawl_error_count"):
        score += 15
    if not run.get("source_error_count"):
        score += 15
    if run.get("brief_included"):
        score += 15
    if run.get("evidence_text_chars", 0) >= MIN_EVIDENCE_TEXT_CHARS:
        score += 15
    if run.get("artifact_path"):
        score += 5
    return min(score, 100)


def quality_status(score: int, warnings: List[str]) -> str:
    if score >= 80 and not warnings:
        return "ready"
    if score >= 40:
        return "partial"
    return "needs_attention"


def review_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    status_counts: Dict[str, int] = {}
    for run in runs:
        status = run.get("quality_status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "success": bool(runs),
        "artifact_count": sum(1 for run in runs if run.get("artifact_path")),
        "status_counts": status_counts,
        "average_score": round(sum(run.get("score", 0) for run in runs) / len(runs), 1) if runs else 0,
    }


def render_batch_report(
    runs: List[Dict[str, Any]],
    review: Dict[str, Any],
    sources: List[str],
    output_dir: str,
) -> str:
    lines = [
        "# Research Batch Workflow Review",
        "",
        f"- Queries: {len(runs)}",
        f"- Sources: {', '.join(sources) if sources else 'auto'}",
        f"- Output dir: `{output_dir}`",
        f"- Average score: `{review.get('average_score', 0)}`",
        f"- Status counts: `{review.get('status_counts') or {}}`",
        "",
    ]
    for run in runs:
        lines.extend(
            [
                f"## {run.get('query') or 'Untitled query'}",
                "",
                f"- Status: `{run.get('quality_status')}`",
                f"- Score: `{run.get('score')}`",
                f"- Artifact: `{run.get('artifact_path') or 'none'}`",
                f"- Brief: `{run.get('brief_path') or 'none'}`",
                (
                    "- Counts: "
                    f"{run.get('successful_document_count', 0)}/{run.get('document_count', 0)} documents usable, "
                    f"{run.get('image_count', 0)} images, "
                    f"{run.get('source_error_count', 0)} source errors, "
                    f"{run.get('crawl_error_count', 0)} crawl errors"
                ),
            ]
        )
        warnings = run.get("warnings") or []
        lines.append(f"- Warnings: {', '.join(f'`{warning}`' for warning in warnings) if warnings else 'none'}")
        if run.get("error"):
            error = run["error"]
            lines.append(f"- Error: `{error.get('code')}` {error.get('message') or ''}".rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_batch_report(content: str, path: str, project_root: str) -> Dict[str, Any]:
    resolved = _resolve_project_file(path or DEFAULT_BATCH_REPORT_PATH, project_root)
    if not resolved.get("success"):
        return resolved
    try:
        os.makedirs(os.path.dirname(resolved["data"]["path"]), exist_ok=True)
        with open(resolved["data"]["path"], "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as ex:
        return _err(f"Failed to write batch review report: {ex}", code="WRITE_ERROR")
    return _ok(
        {
            "format": "markdown",
            "path": _relative_path(resolved["data"]["path"], project_root),
        },
        path=_relative_path(resolved["data"]["path"], project_root),
    )


def _normalize_queries(queries: Iterable[str]) -> List[str]:
    if isinstance(queries, str):
        queries = [queries]
    seen = set()
    selected = []
    for query in queries or []:
        cleaned = clean_text(query)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        selected.append(cleaned)
    return selected


def _batch_error(runs: List[Dict[str, Any]], report_artifact: Dict[str, Any]) -> Dict[str, Any]:
    if not report_artifact.get("success"):
        return report_artifact.get("error") or {"code": "REPORT_WRITE_FAILED", "message": "Report writing failed"}
    failed = next((run for run in runs if not run.get("success")), None)
    if failed:
        return failed.get("error") or {"code": "WORKFLOW_FAILED", "message": "At least one workflow failed"}
    return {"code": "BATCH_FAILED", "message": "Research batch workflow failed"}


def _resolve_project_file(path: str, project_root: str) -> Dict:
    output_path = path
    if not os.path.isabs(output_path):
        output_path = os.path.join(project_root, output_path)
    output_path = os.path.abspath(output_path)
    project_root = os.path.abspath(project_root)
    if os.path.commonpath([project_root, output_path]) != project_root:
        return _err("report_path must stay inside the Argus project directory", code="UNSAFE_REPORT_PATH")
    return _ok({"path": output_path})


def _relative_path(path: Optional[str], project_root: str) -> Optional[str]:
    if not path:
        return None
    absolute_path = os.path.abspath(path)
    project_root = os.path.abspath(project_root)
    try:
        if os.path.commonpath([project_root, absolute_path]) != project_root:
            return None
    except ValueError:
        return None
    return os.path.relpath(absolute_path, project_root)


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}

def _err(message: str, code: str = "RESEARCH_BATCH_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
