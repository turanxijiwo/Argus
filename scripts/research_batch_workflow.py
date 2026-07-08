#!/usr/bin/env python3
"""Run multiple saved Research Toolkit workflows and generate a review report."""

import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

from argus_server.tools.research_handoff import build_batch_handoff


DEFAULT_QUERIES = ["OpenAI"]
DEFAULT_OUTPUT_DIR = "output/research/batch"
DEFAULT_REPORT_PATH = "output/research/artifact-reviews/batch-review.md"


def load_queries(args: argparse.Namespace) -> List[str]:
    queries = []
    for query in args.query or []:
        cleaned = str(query or "").strip()
        if cleaned:
            queries.append(cleaned)
    if args.queries_file:
        queries.extend(read_queries_file(args.queries_file))
    if not queries:
        queries = list(DEFAULT_QUERIES)
    return dedupe_preserving_order(queries)


def read_queries_file(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        payload = json.loads(stripped)
        if not isinstance(payload, list):
            raise ValueError("queries file JSON must be a list")
        return [str(item).strip() for item in payload if str(item).strip()]
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def dedupe_preserving_order(values: Iterable[str]) -> List[str]:
    seen = set()
    selected = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        selected.append(value)
    return selected


def summarize_workflow_result(query: str, result: Dict[str, Any], project_root: str) -> Dict[str, Any]:
    data = result.get("data") or {}
    documents = data.get("documents") or []
    brief = data.get("brief") or {}
    artifact = data.get("artifact") or {}
    brief_artifact = brief.get("artifact") or {}
    return {
        "query": query,
        "success": bool(result.get("success")),
        "artifact_path": _relative_path(artifact.get("path"), project_root),
        "brief_path": _relative_path(brief_artifact.get("path"), project_root),
        "document_count": len(documents),
        "successful_document_count": sum(1 for document in documents if document.get("success")),
        "image_count": len(data.get("images") or []),
        "source_error_count": len(data.get("source_errors") or []),
        "crawl_error_count": sum(1 for document in documents if not document.get("success")),
        "brief_included": bool(brief.get("content")),
        "error": result.get("error") or {},
    }


def run_workflows(args: argparse.Namespace, queries: List[str], project_root: str) -> Dict[str, Any]:
    try:
        from argus_server.server import _get_tools
    except Exception as ex:
        return {
            "success": False,
            "status": "unavailable",
            "tool_error": {
                "code": "TOOL_IMPORT_ERROR",
                "message": f"Research tools could not be imported: {ex}",
            },
            "runs": [],
        }

    research = _get_tools()["research"]
    sources = args.source or ["wikipedia"]
    runs = []
    artifact_paths = []
    review_artifact_paths = []
    for query in queries:
        result = research.research_workflow(
            query,
            sources=sources,
            limit=args.limit,
            timeout=args.timeout,
            max_chars_per_page=args.max_chars_per_page,
            images_per_page=args.images_per_page,
            render_js=False,
            retries=args.retries,
            include_brief=True,
            save=True,
            save_brief=True,
            output_dir=args.output_dir,
        )
        run_summary = summarize_workflow_result(query, result, project_root)
        runs.append(run_summary)
        if run_summary.get("artifact_path"):
            artifact_paths.append(run_summary["artifact_path"])
            review_artifact_paths.append(os.path.join(project_root, run_summary["artifact_path"]))

    return {
        "success": all(run.get("success") for run in runs),
        "status": "ran",
        "sources": sources,
        "runs": runs,
        "artifact_paths": artifact_paths,
        "_review_artifact_paths": review_artifact_paths,
    }


def build_review(artifact_paths: List[str], report_path: str, project_root: str) -> Dict[str, Any]:
    review_module = load_review_module()
    report = review_module.review_collection(artifact_paths, project_root)
    markdown = review_module.render_markdown_report(report)
    write_result = review_module.write_report(markdown, report_path, project_root)
    report["report_artifact"] = write_result
    report["markdown_chars"] = len(markdown)
    return report


def batch_passed(summary: Dict[str, Any]) -> bool:
    workflows = summary.get("workflows") or {}
    review = summary.get("review") or {}
    status_counts = review.get("status_counts") or {}
    return (
        bool(summary.get("success"))
        and workflows.get("status") == "ran"
        and all(run.get("success") for run in workflows.get("runs") or [])
        and bool(review.get("success"))
        and not status_counts.get("unreadable")
        and bool((review.get("report_artifact") or {}).get("success"))
    )


def exit_code_for_summary(summary: Dict[str, Any]) -> int:
    workflows = summary.get("workflows") or {}
    if workflows.get("status") == "unavailable":
        return 2
    return 0 if summary.get("passed") else 3


def run_batch(args: argparse.Namespace) -> int:
    project_root = os.getcwd()
    try:
        queries = load_queries(args)
    except (OSError, json.JSONDecodeError, ValueError) as ex:
        summary = {
            "success": False,
            "passed": False,
            "status": "invalid_queries",
            "error": {"code": ex.__class__.__name__, "message": str(ex)},
        }
        summary["exit_code"] = 3
        summary["handoff"] = build_batch_handoff(
            runs=[],
            query_count=0,
            output_dir=args.output_dir,
            review_report=args.review_report,
            entrypoint="script",
            exit_code=summary["exit_code"],
            ready=False,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return summary["exit_code"]

    workflows = run_workflows(args, queries, project_root)
    review = {}
    review_artifact_paths = workflows.pop("_review_artifact_paths", [])
    if review_artifact_paths:
        review = build_review(review_artifact_paths, args.review_report, project_root)

    summary = {
        "success": bool(workflows.get("success")) and bool(review.get("success")),
        "passed": False,
        "status": workflows.get("status"),
        "query_count": len(queries),
        "output_dir": args.output_dir,
        "review_report": args.review_report,
        "workflows": workflows,
        "review": review,
    }
    summary["passed"] = batch_passed(summary)
    summary["exit_code"] = exit_code_for_summary(summary)
    summary["handoff"] = build_batch_handoff(
        runs=workflows.get("runs") or [],
        artifact_paths=workflows.get("artifact_paths") or [],
        review=review,
        report_artifact=review.get("report_artifact") or {},
        query_count=len(queries),
        output_dir=args.output_dir,
        review_report=args.review_report,
        entrypoint="script",
        exit_code=summary["exit_code"],
        ready=summary["passed"],
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary["exit_code"]


def load_review_module():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    module_path = os.path.join(script_dir, "research_artifact_review.py")
    spec = importlib.util.spec_from_file_location("research_artifact_review", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _path_inside_project(path: Optional[str], project_root: str) -> bool:
    if not path:
        return False
    try:
        return os.path.commonpath([os.path.abspath(project_root), os.path.abspath(path)]) == os.path.abspath(project_root)
    except ValueError:
        return False


def _relative_path(path: Optional[str], project_root: str) -> Optional[str]:
    if not path:
        return None
    if not _path_inside_project(path, project_root):
        return None
    return os.path.relpath(os.path.abspath(path), project_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", help="Research query. May be passed multiple times.")
    parser.add_argument("--queries-file", help="Optional newline or JSON-list file of research queries.")
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        help="Workflow source. May be passed multiple times. Defaults to wikipedia.",
    )
    parser.add_argument("--limit", type=int, default=1, help="Workflow page limit per query.")
    parser.add_argument("--timeout", type=int, default=20, help="Page crawl timeout in seconds.")
    parser.add_argument("--max-chars-per-page", type=int, default=1500, help="Maximum page text characters to keep.")
    parser.add_argument("--images-per-page", type=int, default=5, help="Maximum images to keep per page.")
    parser.add_argument("--retries", type=int, default=1, help="Extra retries for retriable crawl failures.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Project-local directory for saved artifacts.")
    parser.add_argument(
        "--review-report",
        default=DEFAULT_REPORT_PATH,
        help="Project-local Markdown review report path.",
    )
    return parser


def main() -> int:
    return run_batch(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
