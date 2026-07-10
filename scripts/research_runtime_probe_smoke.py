#!/usr/bin/env python3
"""Run explicit optional Research Toolkit runtime probes with stable exit codes."""

import argparse
import json
import sys
from typing import Any, Dict, Iterable, List


DEFAULT_ADAPTERS = ["crawl4ai", "codex"]


def summarize_probe(result: Dict[str, Any], adapters: Iterable[str]) -> Dict[str, Any]:
    probes = ((result.get("data") or {}).get("probes") or {})
    selected = list(adapters or [])
    blocked_codes = {"CONFIG_ERROR", "PERMISSION_ERROR", "NOT_INSTALLED", "IMPORT_ERROR"}
    checks = {
        "top_level_success": bool(result.get("success")),
        "all_requested_probes_returned": all(adapter in probes for adapter in selected),
        "all_runtime_verified": all(probes.get(adapter, {}).get("status") == "runtime_verified" for adapter in selected),
    }
    failures = [probes.get(adapter, {}) for adapter in selected if probes.get(adapter, {}).get("status") != "runtime_verified"]
    failure_codes = [((probe.get("error") or {}).get("code")) for probe in failures]
    status = "ready" if all(checks.values()) else "blocked" if any(code in blocked_codes for code in failure_codes) else "failed"
    return {
        "success": status == "ready",
        "status": status,
        "checks": checks,
        "adapters": selected,
        "probes": probes,
        "failure_codes": failure_codes,
        "error": result.get("error") or {},
    }


def exit_code_for_summary(summary: Dict[str, Any]) -> int:
    if summary.get("success"):
        return 0
    return 2 if summary.get("status") in {"blocked", "unavailable"} else 3


def run_smoke(args: argparse.Namespace) -> int:
    try:
        from argus_server.server import _get_tools
    except Exception as ex:
        summary = {
            "success": False,
            "status": "unavailable",
            "error": {"code": "TOOL_IMPORT_ERROR", "message": str(ex)},
        }
    else:
        adapters = args.adapter or list(DEFAULT_ADAPTERS)
        result = _get_tools()["research"].research_runtime_probe(
            adapters=adapters,
            url=args.url,
            query=args.query,
            timeout=args.timeout,
        )
        summary = summarize_probe(result, adapters)
    summary["exit_code"] = exit_code_for_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary["exit_code"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", action="append", default=None, help="Probe adapter. May be passed multiple times.")
    parser.add_argument("--url", default="https://example.com", help="Public URL for Crawl4AI.")
    parser.add_argument("--query", default="OpenAI research toolkit", help="Query for Codex SDK.")
    parser.add_argument("--timeout", type=int, default=30, help="Crawl4AI timeout in seconds.")
    return parser


def main() -> int:
    return run_smoke(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
