#!/usr/bin/env python3
"""Run a safe real-provider smoke for Research Toolkit web sources."""

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, Mapping, Optional


PROVIDER_ENV_VARS = {
    "tavily": "TAVILY_API_KEY",
    "exa": "EXA_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "brave": "BRAVE_API_KEY",
}


def configured_providers(env: Mapping[str, str]) -> Dict[str, str]:
    return {
        provider: env_var
        for provider, env_var in PROVIDER_ENV_VARS.items()
        if env.get(env_var)
    }


def choose_provider(requested_provider: Optional[str], env: Mapping[str, str]) -> Optional[str]:
    configured = configured_providers(env)
    if requested_provider:
        provider = requested_provider.strip().lower()
        return provider if provider in configured else None
    return next(iter(configured), None)


def summarize_topic(result: Dict[str, Any]) -> Dict[str, Any]:
    data = result.get("data") or {}
    merged = data.get("merged") or []
    source_errors = _source_errors(data.get("sources") or {})
    return {
        "success": bool(result.get("success")),
        "merged_count": len(merged),
        "first_result_has_url": bool(merged[0].get("url")) if merged else False,
        "source_errors": source_errors,
    }


def summarize_packet(result: Dict[str, Any]) -> Dict[str, Any]:
    data = result.get("data") or {}
    documents = data.get("documents") or []
    return {
        "success": bool(result.get("success")),
        "document_count": len(documents),
        "successful_document_count": sum(1 for document in documents if document.get("success")),
        "source_error_count": len(data.get("source_errors") or []),
        "page_error_count": sum(1 for document in documents if not document.get("success")),
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
        "brief_included": bool(brief.get("content")),
    }


def smoke_passed(summary: Dict[str, Any]) -> bool:
    topic = summary.get("topic") or {}
    packet = summary.get("pack") or {}
    workflow = summary.get("workflow") or {}
    return (
        topic.get("success")
        and topic.get("first_result_has_url")
        and packet.get("success")
        and packet.get("successful_document_count", 0) > 0
        and workflow.get("success")
        and workflow.get("successful_document_count", 0) > 0
    )


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


def run_smoke(args: argparse.Namespace) -> int:
    provider = choose_provider(args.provider, os.environ)
    configured = configured_providers(os.environ)
    if not provider:
        print(
            json.dumps(
                {
                    "success": False,
                    "status": "skipped",
                    "reason": "NO_CONFIGURED_PROVIDER",
                    "requested_provider": args.provider,
                    "configured_providers": sorted(configured),
                    "required_env_vars": PROVIDER_ENV_VARS,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    from argus_server.server import _get_tools

    source = f"web:{provider}"
    research = _get_tools()["research"]

    topic_result = research.research_topic(args.query, sources=[source], limit=args.limit)
    pack_result = research.research_pack(
        args.query,
        sources=[source],
        limit=args.limit,
        timeout=args.timeout,
        max_chars_per_page=args.max_chars_per_page,
    )
    workflow_result = research.research_workflow(
        args.query,
        sources=[source],
        limit=args.limit,
        timeout=args.timeout,
        max_chars_per_page=args.max_chars_per_page,
        images_per_page=args.images_per_page,
        include_brief=True,
        save=False,
    )

    summary = {
        "success": True,
        "status": "ran",
        "provider": provider,
        "source": source,
        "query": args.query,
        "topic": summarize_topic(topic_result),
        "pack": summarize_packet(pack_result),
        "workflow": summarize_workflow(workflow_result),
    }
    summary["passed"] = smoke_passed(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["passed"] else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=sorted(PROVIDER_ENV_VARS), help="Provider to test. Defaults to the first configured provider.")
    parser.add_argument("--query", default="OpenAI research toolkit", help="Smoke-test query.")
    parser.add_argument("--limit", type=int, default=1, help="Result/page limit for each chain.")
    parser.add_argument("--timeout", type=int, default=20, help="Page crawl timeout in seconds.")
    parser.add_argument("--max-chars-per-page", type=int, default=1500, help="Maximum page text characters to keep.")
    parser.add_argument("--images-per-page", type=int, default=3, help="Maximum images to keep per page.")
    return parser


def main() -> int:
    return run_smoke(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
