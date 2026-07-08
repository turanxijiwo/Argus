#!/usr/bin/env python3
"""Run repeatable public-page quality smokes for the Research Toolkit."""

import argparse
import json
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional


DEFAULT_FIXTURES = [
    {
        "name": "example_domain",
        "url": "https://example.com/",
        "title_contains": "Example Domain",
        "min_text_chars": 40,
        "min_links": 1,
        "min_images": 0,
    },
    {
        "name": "iana_reserved_domains",
        "url": "https://www.iana.org/domains/reserved",
        "title_contains": "IANA-managed Reserved Domains",
        "min_text_chars": 400,
        "min_links": 1,
        "min_images": 0,
    },
]


def summarize_crawl(result: Dict[str, Any], fixture: Mapping[str, Any]) -> Dict[str, Any]:
    data = result.get("data") or {}
    summary = result.get("summary") or {}
    title = data.get("title") or ""
    text = data.get("text") or ""
    links = data.get("links") or []
    images = data.get("images") or []
    checks = {
        "success": bool(result.get("success")),
        "title_contains": _contains(title, fixture.get("title_contains")),
        "min_text_chars": len(text) >= int(fixture.get("min_text_chars", 0)),
        "min_links": len(links) >= int(fixture.get("min_links", 0)),
        "min_images": len(images) >= int(fixture.get("min_images", 0)),
    }
    return {
        "success": bool(result.get("success")),
        "url": fixture.get("url"),
        "final_url": data.get("final_url"),
        "status_code": data.get("status_code"),
        "title": title,
        "text_chars": summary.get("text_chars", len(text)),
        "link_count": summary.get("link_count", len(links)),
        "image_count": summary.get("image_count", len(images)),
        "checks": checks,
        "passed": all(checks.values()),
        "error": result.get("error") or {},
    }


def summarize_image_discovery(result: Dict[str, Any], fixture: Mapping[str, Any]) -> Dict[str, Any]:
    data = result.get("data") or {}
    images = data.get("images") or []
    checks = {
        "success": bool(result.get("success")),
        "min_images": len(images) >= int(fixture.get("min_images", 0)),
    }
    return {
        "success": bool(result.get("success")),
        "page_url": data.get("page_url"),
        "image_count": len(images),
        "checks": checks,
        "passed": all(checks.values()),
        "error": result.get("error") or {},
    }


def summarize_fixture(
    fixture: Mapping[str, Any],
    crawl_result: Dict[str, Any],
    image_result: Dict[str, Any],
) -> Dict[str, Any]:
    crawl = summarize_crawl(crawl_result, fixture)
    image_discovery = summarize_image_discovery(image_result, fixture)
    return {
        "name": fixture.get("name"),
        "url": fixture.get("url"),
        "crawl": crawl,
        "image_discovery": image_discovery,
        "passed": crawl["passed"] and image_discovery["passed"],
    }


def summarize_workflow(result: Dict[str, Any]) -> Dict[str, Any]:
    data = result.get("data") or {}
    documents = data.get("documents") or []
    successful_document_count = sum(1 for document in documents if document.get("success"))
    brief = data.get("brief") or {}
    checks = {
        "success": bool(result.get("success")),
        "has_document": len(documents) > 0,
        "has_successful_document": successful_document_count > 0,
        "brief_included": bool(brief.get("content")),
        "no_source_errors": len(data.get("source_errors") or []) == 0,
    }
    return {
        "success": bool(result.get("success")),
        "document_count": len(documents),
        "successful_document_count": successful_document_count,
        "image_count": len(data.get("images") or []),
        "source_error_count": len(data.get("source_errors") or []),
        "crawl_error_count": sum(1 for document in documents if not document.get("success")),
        "brief_included": bool(brief.get("content")),
        "checks": checks,
        "passed": all(checks.values()),
        "error": result.get("error") or {},
    }


def smoke_passed(summary: Dict[str, Any]) -> bool:
    fixtures = summary.get("fixtures") or []
    workflow = summary.get("workflow") or {}
    return bool(fixtures) and all(item.get("passed") for item in fixtures) and bool(workflow.get("passed"))


def exit_code_for_summary(summary: Dict[str, Any]) -> int:
    if summary.get("passed"):
        return 0
    if summary.get("status") == "unavailable":
        return 2
    return 3


def selected_fixtures(names: Optional[Iterable[str]]) -> List[Dict[str, Any]]:
    if not names:
        return list(DEFAULT_FIXTURES)
    requested = {name.strip() for name in names if name and name.strip()}
    return [fixture for fixture in DEFAULT_FIXTURES if fixture["name"] in requested]


def run_smoke(args: argparse.Namespace) -> int:
    if args.list_fixtures:
        print(json.dumps({"fixtures": DEFAULT_FIXTURES}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    try:
        from argus_server.server import _get_tools
    except Exception as ex:
        summary = {
            "success": False,
            "passed": False,
            "status": "unavailable",
            "tool_error": {
                "code": "TOOL_IMPORT_ERROR",
                "message": f"Research tools could not be imported: {ex}",
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    fixtures = selected_fixtures(args.fixture)
    if not fixtures:
        summary = {
            "success": False,
            "passed": False,
            "status": "failed",
            "error": {
                "code": "NO_SELECTED_FIXTURES",
                "message": "No matching public crawl fixtures were selected",
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 3

    research = _get_tools()["research"]
    fixture_summaries = []
    for fixture in fixtures:
        crawl_result = research.crawl_url(
            fixture["url"],
            render_js=False,
            timeout=args.timeout,
            max_chars=args.max_chars_per_page,
        )
        image_result = research.discover_page_images(
            fixture["url"],
            timeout=args.timeout,
            limit=args.images_per_page,
        )
        fixture_summaries.append(summarize_fixture(fixture, crawl_result, image_result))

    workflow_result = research.research_workflow(
        args.workflow_query,
        sources=["wikipedia"],
        limit=args.workflow_limit,
        timeout=args.timeout,
        max_chars_per_page=args.max_chars_per_page,
        images_per_page=args.images_per_page,
        include_brief=True,
        save=False,
    )
    summary = {
        "success": False,
        "passed": False,
        "status": "ran",
        "fixtures": fixture_summaries,
        "workflow": summarize_workflow(workflow_result),
    }
    summary["passed"] = smoke_passed(summary)
    summary["success"] = summary["passed"]
    summary["exit_code"] = exit_code_for_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary["exit_code"]


def _contains(value: str, expected: Any) -> bool:
    if expected in (None, ""):
        return True
    return str(expected).lower() in str(value or "").lower()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        action="append",
        choices=[fixture["name"] for fixture in DEFAULT_FIXTURES],
        help="Fixture to run. May be passed multiple times. Defaults to all fixtures.",
    )
    parser.add_argument("--list-fixtures", action="store_true", help="Print default public fixtures and exit.")
    parser.add_argument("--timeout", type=int, default=20, help="Page crawl timeout in seconds.")
    parser.add_argument("--max-chars-per-page", type=int, default=1500, help="Maximum page text characters to keep.")
    parser.add_argument("--images-per-page", type=int, default=5, help="Maximum images to inspect per page.")
    parser.add_argument("--workflow-query", default="OpenAI", help="Public workflow smoke query.")
    parser.add_argument("--workflow-limit", type=int, default=1, help="Public workflow page limit.")
    return parser


def main() -> int:
    return run_smoke(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
