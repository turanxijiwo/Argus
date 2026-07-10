#!/usr/bin/env python3
"""Smoke-test a batch research handoff into a selected artifact review."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List


DEFAULT_QUERIES = ["OpenAI", "Artificial intelligence"]
DEFAULT_OUTPUT_DIR = "output/research/batch-handoff-smoke"
DEFAULT_REPORT_PATH = "output/research/artifact-reviews/batch-handoff-smoke.md"


def summarize_batch_review(batch_result: Dict[str, Any], review_result: Dict[str, Any], artifact_index: int) -> Dict[str, Any]:
    batch_data = batch_result.get("data") or {}
    batch_handoff = batch_data.get("handoff") or {}
    review_data = review_result.get("data") or {}
    review_handoff = review_data.get("handoff") or {}
    artifact_paths = batch_handoff.get("artifact_paths") or []
    selected_path = artifact_paths[artifact_index] if 0 <= artifact_index < len(artifact_paths) else None
    checks = {
        "batch_success": bool(batch_result.get("success")),
        "batch_handoff_schema": batch_handoff.get("schema") == "argus.research.batch.handoff.v1",
        "batch_handoff_ready": bool(batch_handoff.get("ready")),
        "batch_artifact_count": len(artifact_paths) >= 2,
        "selected_artifact_exists": bool(selected_path),
        "review_success": bool(review_result.get("success")),
        "review_handoff_schema": review_handoff.get("schema") == "argus.research.review.handoff.v1",
        "review_path_matches_selected": review_handoff.get("artifact_path") == selected_path,
        "review_quality_ready": review_data.get("quality_status") == "ready",
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "selected_artifact_index": artifact_index,
        "batch_handoff": batch_handoff,
        "review_handoff": review_handoff,
        "review_quality_status": review_data.get("quality_status"),
        "review_score": review_data.get("score"),
        "review_warnings": review_data.get("warnings") or [],
        "errors": {
            "batch": batch_result.get("error") or {},
            "review": review_result.get("error") or {},
        },
    }


def exit_code_for_summary(summary: Dict[str, Any]) -> int:
    if summary.get("passed"):
        return 0
    if summary.get("status") == "unavailable":
        return 2
    return 3


def run_smoke(args: argparse.Namespace) -> int:
    try:
        from argus_server.server import _get_tools
    except Exception as ex:
        summary = {
            "success": False,
            "passed": False,
            "status": "unavailable",
            "error": {"code": "TOOL_IMPORT_ERROR", "message": str(ex)},
        }
        summary["exit_code"] = exit_code_for_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return summary["exit_code"]

    queries = args.query or list(DEFAULT_QUERIES)
    research = _get_tools()["research"]
    batch_result = research.research_batch_workflow(
        queries=queries,
        sources=args.source or ["wikipedia"],
        limit=args.limit,
        timeout=args.timeout,
        max_chars_per_page=args.max_chars_per_page,
        images_per_page=args.images_per_page,
        render_js=False,
        retries=args.retries,
        output_dir=args.output_dir,
        report_path=args.report_path,
    )
    review_result = research.research_review_artifact(
        handoff=((batch_result.get("data") or {}).get("handoff") or {}),
        artifact_index=args.artifact_index,
    )
    summary = summarize_batch_review(batch_result, review_result, args.artifact_index)
    summary.update(
        {
            "success": summary["passed"],
            "status": "ran",
            "queries": queries,
            "sources": args.source or ["wikipedia"],
            "output_dir": args.output_dir,
        }
    )
    summary["exit_code"] = exit_code_for_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary["exit_code"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", default=None, help="Research query. May be passed multiple times.")
    parser.add_argument("--source", action="append", default=None, help="Source. Defaults to wikipedia.")
    parser.add_argument("--artifact-index", type=int, default=1, help="Batch artifact index to review.")
    parser.add_argument("--limit", type=int, default=1, help="Workflow page limit per query.")
    parser.add_argument("--timeout", type=int, default=20, help="Page crawl timeout in seconds.")
    parser.add_argument("--max-chars-per-page", type=int, default=1500, help="Maximum page text characters to keep.")
    parser.add_argument("--images-per-page", type=int, default=5, help="Maximum images to keep per page.")
    parser.add_argument("--retries", type=int, default=1, help="Extra retries for retriable crawl failures.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Project-local artifact directory.")
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH, help="Project-local batch review report path.")
    return parser


def main() -> int:
    return run_smoke(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
