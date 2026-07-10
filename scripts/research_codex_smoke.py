#!/usr/bin/env python3
"""Run a safe Codex-source smoke for the Research Toolkit workflow."""

import argparse
import json
import sys
from typing import Any, Dict, Iterable, Mapping


RUNTIME_UNAVAILABLE_CODES = {
    "NOT_INSTALLED",
    "IMPORT_ERROR",
    "CODEX_SDK_ERROR",
    "CODEX_RUNNER_ERROR",
    "TOOL_IMPORT_ERROR",
}


def summarize_topic(result: Dict[str, Any]) -> Dict[str, Any]:
    data = result.get("data") or {}
    merged = data.get("merged") or []
    source_errors = _source_errors(data.get("sources") or {})
    return {
        "success": bool(result.get("success")),
        "merged_count": len(merged),
        "first_result_has_url": bool(merged[0].get("url")) if merged else False,
        "source_errors": source_errors,
        "top_level_error": _top_level_error(result),
    }


def summarize_workflow(result: Dict[str, Any]) -> Dict[str, Any]:
    data = result.get("data") or {}
    documents = data.get("documents") or []
    brief = data.get("brief") or {}
    return {
        "success": bool(result.get("success")),
        "document_count": len(documents),
        "successful_document_count": sum(1 for document in documents if document.get("success")),
        "image_count": len(data.get("images") or []),
        "source_error_count": len(data.get("source_errors") or []),
        "source_errors": data.get("source_errors") or [],
        "brief_included": bool(brief.get("content")),
        "top_level_error": _top_level_error(result),
    }


def smoke_passed(summary: Dict[str, Any]) -> bool:
    topic = summary.get("topic") or {}
    workflow = summary.get("workflow") or {}
    workflow_passed = (
        topic.get("success")
        and topic.get("first_result_has_url")
        and workflow.get("success")
        and workflow.get("successful_document_count", 0) > 0
    )
    if not summary.get("save"):
        return workflow_passed
    return workflow_passed and bool((summary.get("review") or {}).get("passed"))


def summarize_review(workflow_result: Dict[str, Any], review_result: Dict[str, Any]) -> Dict[str, Any]:
    workflow_handoff = ((workflow_result.get("data") or {}).get("handoff") or {})
    review_data = review_result.get("data") or {}
    review_handoff = review_data.get("handoff") or {}
    checks = {
        "workflow_handoff_ready": bool(workflow_handoff.get("ready")),
        "review_success": bool(review_result.get("success")),
        "review_handoff_schema": review_handoff.get("schema") == "argus.research.review.handoff.v1",
        "review_path_matches_workflow": review_handoff.get("artifact_path") == workflow_handoff.get("artifact_path"),
        "review_quality_ready": review_data.get("quality_status") == "ready",
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "quality_status": review_data.get("quality_status"),
        "score": review_data.get("score"),
        "warnings": review_data.get("warnings") or [],
        "error": review_result.get("error") or {},
    }


def exit_code_for_summary(summary: Dict[str, Any]) -> int:
    if summary.get("passed"):
        return 0
    if _has_runtime_unavailable_error(summary):
        return 2
    return 3


def run_smoke(args: argparse.Namespace) -> int:
    try:
        from argus_server.server import _get_tools
    except Exception as ex:
        summary = {
            "success": False,
            "status": "unavailable",
            "source": "codex",
            "query": args.query,
            "tool_error": {
                "code": "TOOL_IMPORT_ERROR",
                "message": f"Research tools could not be imported: {ex}",
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    research = _get_tools()["research"]

    topic_result = research.research_topic(args.query, sources=["codex"], limit=args.limit)
    summary = {
        "success": False,
        "status": "ran",
        "source": "codex",
        "query": args.query,
        "topic": summarize_topic(topic_result),
        "workflow": None,
    }

    topic = summary["topic"]
    if topic.get("success") and topic.get("first_result_has_url"):
        workflow_result = research.research_workflow(
            args.query,
            sources=["codex"],
            limit=args.limit,
            timeout=args.timeout,
            max_chars_per_page=args.max_chars_per_page,
            images_per_page=args.images_per_page,
            include_brief=True,
            save=args.save,
            save_brief=args.save,
            output_dir=args.output_dir,
        )
        summary["workflow"] = summarize_workflow(workflow_result)
        if args.save:
            review_result = research.research_review_artifact(
                handoff=((workflow_result.get("data") or {}).get("handoff") or {}),
            )
            summary["review"] = summarize_review(workflow_result, review_result)

    summary["save"] = args.save
    summary["output_dir"] = args.output_dir if args.save else None
    summary["passed"] = smoke_passed(summary)
    summary["success"] = summary["passed"]
    summary["exit_code"] = exit_code_for_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary["exit_code"]


def _source_errors(sources: Mapping[str, Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    errors = []
    for source_name, source_result in sources.items():
        if source_result.get("success"):
            continue
        error = source_result.get("error") or {}
        errors.append(
            {
                "source": source_name,
                "code": error.get("code"),
                "message": error.get("message"),
            }
        )
    return errors


def _top_level_error(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("success"):
        return {}
    error = result.get("error") or {}
    return {"code": error.get("code"), "message": error.get("message")}


def _has_runtime_unavailable_error(summary: Dict[str, Any]) -> bool:
    for error in _summary_errors(summary):
        if error.get("code") in RUNTIME_UNAVAILABLE_CODES:
            return True
    return False


def _summary_errors(summary: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    tool_error = summary.get("tool_error")
    if isinstance(tool_error, dict):
        yield tool_error

    for section_name in ("topic", "workflow", "review"):
        section = summary.get(section_name) or {}
        top_level_error = section.get("top_level_error")
        if isinstance(top_level_error, dict) and top_level_error:
            yield top_level_error
        for error in section.get("source_errors") or []:
            if isinstance(error, dict):
                yield error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="OpenAI research toolkit", help="Smoke-test query.")
    parser.add_argument("--limit", type=int, default=1, help="Result/page limit for the chain.")
    parser.add_argument("--timeout", type=int, default=20, help="Page crawl timeout in seconds.")
    parser.add_argument("--max-chars-per-page", type=int, default=1500, help="Maximum page text characters to keep.")
    parser.add_argument("--images-per-page", type=int, default=3, help="Maximum images to keep per page.")
    parser.add_argument("--save", action="store_true", help="Save JSON/Markdown artifacts and verify their review handoff.")
    parser.add_argument("--output-dir", default="output/research/codex-smoke", help="Project-local saved artifact directory.")
    return parser


def main() -> int:
    return run_smoke(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
