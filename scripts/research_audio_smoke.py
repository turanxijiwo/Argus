#!/usr/bin/env python3
"""Run a repeatable metadata-only smoke through the research_audio MCP tool."""

import argparse
import asyncio
import json
import sys
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit


AUDIO_SOURCE = "audio:openverse"
MCP_TOOL = "research_audio"
UNAVAILABLE_ERROR_CODES = {"HTTP_ERROR", "NETWORK_ERROR", "RATE_LIMITED", "TIMEOUT"}
FORBIDDEN_MEDIA_FIELDS = {"alt_files", "audio_bytes", "lyrics", "transcript", "waveform"}


def summarize_audio(result: Dict[str, Any], min_results: int) -> Dict[str, Any]:
    raw_data = result.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}
    raw_audio_items = data.get("audio")
    audio_shape_valid = isinstance(raw_audio_items, list) and all(
        isinstance(item, dict) for item in raw_audio_items
    )
    audio_items = raw_audio_items if audio_shape_valid else []
    audio_urls = [str(item.get("audio_url") or "") for item in audio_items]
    raw_error = result.get("error")
    error = raw_error if isinstance(raw_error, dict) else {}
    error_code = str(error.get("code") or "")

    checks = {
        "success": bool(result.get("success")),
        "audio_list": audio_shape_valid,
        "min_results": len(audio_items) >= min_results,
        "unique_audio_urls": len(set(audio_urls)) == len(audio_urls),
        "http_audio_urls": bool(audio_items)
        and all(_is_http_url(url) for url in audio_urls),
        "http_source_pages": bool(audio_items)
        and all(_is_http_url(item.get("source_page_url")) for item in audio_items),
        "openverse_source": bool(audio_items)
        and all(item.get("source") == AUDIO_SOURCE for item in audio_items),
        "non_mature": bool(audio_items)
        and all(item.get("mature") is False for item in audio_items),
        "license_metadata": bool(audio_items)
        and all(_has_license_metadata(item) for item in audio_items),
        "license_verification_required": bool(audio_items)
        and all(item.get("license_verification_required") is True for item in audio_items),
        "provider_notice": bool(data.get("provider_notice")),
        "license_notice": bool(data.get("license_notice")),
        "rate_limit": bool(data.get("rate_limit")),
        "metadata_only": all(
            not FORBIDDEN_MEDIA_FIELDS.intersection(item)
            for item in audio_items
        ),
        "no_media_download": True,
    }
    summary = {
        "success": bool(result.get("success")),
        "audio_count": len(audio_items),
        "unique_audio_count": len(set(audio_urls)),
        "providers": sorted(
            {str(item.get("provider")) for item in audio_items if item.get("provider")}
        ),
        "licenses": sorted(
            {str(item.get("license")) for item in audio_items if item.get("license")}
        ),
        "download_requested": False,
        "checks": checks,
        "error": error,
        "error_code": error_code,
    }
    summary["passed"] = all(checks.values())
    summary["status"] = status_for_summary(summary)
    summary["exit_code"] = exit_code_for_summary(summary)
    return summary


def status_for_summary(summary: Dict[str, Any]) -> str:
    if summary.get("passed"):
        return "passed"
    if summary.get("error_code") in UNAVAILABLE_ERROR_CODES:
        return "unavailable"
    return "failed"


def exit_code_for_summary(summary: Dict[str, Any]) -> int:
    if summary.get("passed"):
        return 0
    if summary.get("status") == "unavailable":
        return 2
    return 3


async def invoke_registered_audio(
    query: str,
    limit: int,
    timeout: int,
    mcp_server: Optional[Any] = None,
) -> Dict[str, Any]:
    if mcp_server is None:
        from argus_server.server import mcp as mcp_server

    tool = await mcp_server.get_tool(MCP_TOOL)
    response = await tool.run({"query": query, "limit": limit, "timeout": timeout})
    content = getattr(response, "content", None) or []
    text = getattr(content[0], "text", None) if content else None
    if not isinstance(text, str):
        raise ValueError("research_audio MCP response is missing text content")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("research_audio MCP response must contain a JSON object")
    return payload


def run_smoke(
    args: argparse.Namespace,
    invoke_audio: Optional[Callable[[str, int, int], Dict[str, Any]]] = None,
) -> int:
    try:
        if invoke_audio is None:
            result = asyncio.run(
                invoke_registered_audio(args.query, args.limit, args.timeout)
            )
        else:
            result = invoke_audio(args.query, args.limit, args.timeout)
    except (ImportError, ModuleNotFoundError, OSError) as exc:
        return _print_invocation_error(args, "MCP_UNAVAILABLE", exc, exit_code=2)
    except Exception as exc:
        return _print_invocation_error(args, "MCP_CONTRACT_ERROR", exc, exit_code=3)

    if not isinstance(result, dict):
        return _print_invocation_error(
            args,
            "MCP_CONTRACT_ERROR",
            ValueError("research_audio MCP result must be a JSON object"),
            exit_code=3,
        )

    summary = summarize_audio(result, min_results=args.min_results)
    summary.update(
        {
            "query": args.query,
            "source": AUDIO_SOURCE,
            "mcp_tool": MCP_TOOL,
            "limit": args.limit,
            "min_results": args.min_results,
        }
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary["exit_code"]


def _print_invocation_error(
    args: argparse.Namespace,
    code: str,
    error: Exception,
    exit_code: int,
) -> int:
    summary = {
        "success": False,
        "passed": False,
        "status": "unavailable" if exit_code == 2 else "failed",
        "exit_code": exit_code,
        "query": args.query,
        "source": AUDIO_SOURCE,
        "mcp_tool": MCP_TOOL,
        "download_requested": False,
        "tool_error": {"code": code, "message": str(error)},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def _has_license_metadata(item: Dict[str, Any]) -> bool:
    return all(item.get(field) for field in ("license", "license_url", "attribution"))


def _is_http_url(value: Any) -> bool:
    parsed = urlsplit(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="birdsong", help="Openverse audio query.")
    parser.add_argument(
        "--limit", type=int, choices=range(1, 21), default=2, help="Result limit (1-20)."
    )
    parser.add_argument(
        "--min-results",
        type=int,
        choices=range(1, 21),
        default=1,
        help="Minimum acceptable result count (1-20).",
    )
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout in seconds.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.min_results > args.limit:
        parser.error("--min-results cannot exceed --limit")
    return run_smoke(args)


if __name__ == "__main__":
    sys.exit(main())
