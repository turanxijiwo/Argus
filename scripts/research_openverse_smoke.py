#!/usr/bin/env python3
"""Run a repeatable anonymous Openverse image-quality smoke."""

import argparse
import json
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlsplit


OPENVERSE_SOURCE = "image:openverse"
UNAVAILABLE_ERROR_CODES = {"HTTP_ERROR", "NETWORK_ERROR", "RATE_LIMITED", "TIMEOUT"}


def summarize_images(result: Dict[str, Any], min_results: int) -> Dict[str, Any]:
    data = result.get("data") or {}
    images = data.get("images") or []
    source_errors = data.get("source_errors") or []
    source_result = (data.get("sources") or {}).get(OPENVERSE_SOURCE) or {}
    source_data = source_result.get("data") or {}
    image_urls = [image.get("image_url") for image in images]

    checks = {
        "success": bool(result.get("success")),
        "min_results": len(images) >= min_results,
        "unique_image_urls": len(set(image_urls)) == len(image_urls),
        "http_image_urls": bool(images) and all(_is_http_url(url) for url in image_urls),
        "http_source_pages": bool(images)
        and all(_is_http_url(image.get("source_page_url")) for image in images),
        "openverse_source": bool(images)
        and all(image.get("source") == OPENVERSE_SOURCE for image in images),
        "non_mature": bool(images) and all(image.get("mature") is False for image in images),
        "license_metadata": bool(images) and all(_has_license_metadata(image) for image in images),
        "license_verification_required": bool(images)
        and all(image.get("license_verification_required") is True for image in images),
        "provider_notice": bool(source_data.get("provider_notice")),
        "license_notice": bool(source_data.get("license_notice")),
        "rate_limit": bool(source_data.get("rate_limit")),
        "no_source_errors": not source_errors,
        "no_media_download": True,
    }
    error_codes = sorted(
        {
            error.get("code")
            for error in source_errors
            if isinstance(error, dict) and error.get("code")
        }
    )
    summary = {
        "success": bool(result.get("success")),
        "image_count": len(images),
        "unique_image_count": len(set(image_urls)),
        "source_error_count": len(source_errors),
        "source_error_codes": error_codes,
        "providers": sorted({image.get("provider") for image in images if image.get("provider")}),
        "licenses": sorted({image.get("license") for image in images if image.get("license")}),
        "download_requested": False,
        "checks": checks,
        "error": result.get("error") or {},
    }
    summary["passed"] = all(checks.values())
    summary["status"] = status_for_summary(summary)
    summary["exit_code"] = exit_code_for_summary(summary)
    return summary


def status_for_summary(summary: Dict[str, Any]) -> str:
    if summary.get("passed"):
        return "passed"
    error_codes = set(summary.get("source_error_codes") or [])
    if error_codes and error_codes.issubset(UNAVAILABLE_ERROR_CODES):
        return "unavailable"
    return "failed"


def exit_code_for_summary(summary: Dict[str, Any]) -> int:
    if summary.get("passed"):
        return 0
    if summary.get("status") == "unavailable":
        return 2
    return 3


def run_smoke(args: argparse.Namespace, research: Optional[Any] = None) -> int:
    if research is None:
        try:
            from argus_server.server import _get_tools

            research = _get_tools()["research"]
        except Exception as ex:
            summary = {
                "success": False,
                "passed": False,
                "status": "unavailable",
                "exit_code": 2,
                "tool_error": {
                    "code": "TOOL_IMPORT_ERROR",
                    "message": f"Research tools could not be imported: {ex}",
                },
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            return 2

    result = research.research_images(
        args.query,
        sources=[OPENVERSE_SOURCE],
        limit=args.limit,
        timeout=args.timeout,
    )
    summary = summarize_images(result, min_results=args.min_results)
    summary.update(
        {
            "query": args.query,
            "source": OPENVERSE_SOURCE,
            "limit": args.limit,
            "min_results": args.min_results,
        }
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary["exit_code"]


def _has_license_metadata(image: Dict[str, Any]) -> bool:
    return all(image.get(field) for field in ("license", "license_url", "attribution"))


def _is_http_url(value: Any) -> bool:
    parsed = urlsplit(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="Tsinghua University", help="Openverse smoke query.")
    parser.add_argument("--limit", type=int, choices=range(1, 21), default=3, help="Result limit (1-20).")
    parser.add_argument("--min-results", type=int, choices=range(1, 21), default=1, help="Minimum acceptable result count (1-20).")
    parser.add_argument("--timeout", type=int, default=20, help="Openverse request timeout in seconds.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.min_results > args.limit:
        build_parser().error("--min-results cannot exceed --limit")
    return run_smoke(args)


if __name__ == "__main__":
    sys.exit(main())
