"""Capability health matrix helpers for Argus research tools."""

import importlib.util
import os
import shutil
from typing import Any, Dict


def toolkit_health(
    external_api: Any = None,
    search_tools: Any = None,
    ai_search: Any = None,
    codex_runner: Any = None,
) -> Dict:
    """Return capability readiness, missing setup, and optional adapter status."""
    status = optional_tool_status()
    api_providers = web_search_provider_status()
    configured_web_sources = [
        f"web:{name}" for name, provider in api_providers.items()
        if provider["configured"]
    ]
    crawl4ai_ready = status["crawl4ai"]["installed"]
    gallery_ready = status["gallery-dl"]["installed"]
    web_search_ready = bool(ai_search and configured_web_sources)
    codex_ready = bool(codex_runner or status["openai-codex"]["installed"])
    topic_source_ready = bool(search_tools or external_api or web_search_ready or codex_ready)

    data = {
            "built_in": {
                "crawl_url": "HTTP HTML fetch + text/link/image extraction, optional Crawl4AI rendering when render_js=True",
                "discover_page_images": "image candidate extraction from HTML",
                "research_topic": "cross-source normalized research aggregation, including optional web:<provider> and codex sources",
                "research_pack": "topic search plus page crawling into an evidence packet",
                "research_images": "query-driven page discovery plus normalized image candidate extraction",
                "research_workflow": "one-call topic search, page crawl, image extraction, markdown brief, retry summary, and optional export",
                "research_batch_workflow": "multi-query saved research workflows plus compact artifact review report",
                "research_review_artifact": "compact quality review for one saved JSON research artifact",
                "research_runtime_probe": "explicit optional Crawl4AI/Codex runtime verification",
                "find_research_resource": "access-aware book, paper, and official course discovery",
                "research_resource_workflow": "public resource selection, reading, optional Codex summary, and artifact export",
                "research_compare_artifacts": "saved-artifact comparison with structurally validated source citations",
                "download_gallery": "safe gallery-dl wrapper when installed",
            },
            "web_search_sources": ["web", "web:tavily", "web:exa", "web:perplexity", "web:brave"],
            "research_sources": [
                "local_news",
                "hackernews",
                "wikipedia",
                "reddit:<subreddit>",
                "github_code",
                "web",
                "web:<tavily|exa|perplexity|brave>",
                "codex",
            ],
            "capabilities": {
                "crawl_url": _capability(
                    can_use_now=True,
                    status="ready",
                    mode="built_in_http",
                ),
                "crawl_url_render_js": _capability(
                    can_use_now=crawl4ai_ready,
                    status="ready" if crawl4ai_ready else "needs_setup",
                    missing=[] if crawl4ai_ready else ["crawl4ai"],
                    setup_hint=None if crawl4ai_ready else status["crawl4ai"]["install_hint"],
                ),
                "discover_page_images": _capability(
                    can_use_now=True,
                    status="ready",
                    mode="built_in_html",
                ),
                "research_topic": _capability(
                    can_use_now=topic_source_ready,
                    status="ready" if topic_source_ready else "needs_adapter",
                    missing=[] if topic_source_ready else ["search_tools, external_api, or configured web search provider"],
                    setup_hint=None if topic_source_ready else "Run through argus-mcp or configure a web provider API key",
                ),
                "research_topic_web": _capability(
                    can_use_now=web_search_ready,
                    status="ready" if web_search_ready else "needs_api_key",
                    missing=[] if web_search_ready else ["TAVILY_API_KEY, EXA_API_KEY, PERPLEXITY_API_KEY, or BRAVE_API_KEY"],
                    setup_hint=None if web_search_ready else "Set one web-search API key, or use the codex source when the local Codex SDK is available",
                    available_sources=configured_web_sources,
                ),
                "research_topic_codex": _capability(
                    can_use_now=codex_ready,
                    status="ready" if codex_ready else "needs_setup",
                    missing=[] if codex_ready else ["openai-codex"],
                    setup_hint=None if codex_ready else "Install openai-codex; ARGUS_CODEX_MODEL can override the default model",
                    model=os.environ.get("ARGUS_CODEX_MODEL") or "gpt-5.4",
                ),
                "research_images": _capability(
                    can_use_now=topic_source_ready,
                    status="ready" if topic_source_ready else "needs_source",
                    missing=[] if topic_source_ready else ["a topic source that returns page URLs"],
                    setup_hint=None if topic_source_ready else "Use non-web sources with URLs, configure a web-search provider, or install the local Codex SDK",
                ),
                "research_pack": _capability(
                    can_use_now=topic_source_ready,
                    status="ready" if topic_source_ready else "needs_source",
                    missing=[] if topic_source_ready else ["a topic source that returns page URLs"],
                    setup_hint=None if topic_source_ready else "Use non-web sources with URLs, configure a web-search provider, or install the local Codex SDK",
                ),
                "research_workflow": _capability(
                    can_use_now=topic_source_ready,
                    status="ready" if topic_source_ready else "needs_source",
                    missing=[] if topic_source_ready else ["a topic source that returns page URLs"],
                    setup_hint=None if topic_source_ready else "Use configured web search, the local Codex SDK, or Argus local/external sources",
                ),
                "research_batch_workflow": _capability(
                    can_use_now=topic_source_ready,
                    status="ready" if topic_source_ready else "needs_source",
                    missing=[] if topic_source_ready else ["a topic source that returns page URLs"],
                    setup_hint=None if topic_source_ready else "Use configured web search, the local Codex SDK, or Argus local/external sources",
                ),
                "research_review_artifact": _capability(
                    can_use_now=True,
                    status="ready",
                    mode="project_local_json_review",
                ),
                "research_runtime_probe": _capability(
                    can_use_now=True,
                    status="ready",
                    mode="explicit_opt_in_runtime_probe",
                    note="Package detection does not prove runtime compatibility; call research_runtime_probe to verify.",
                ),
                "find_research_resource": _capability(
                    can_use_now=True,
                    status="ready",
                    mode="access_aware_resource_discovery",
                    resource_types={
                        "book": "ready",
                        "paper": "ready" if external_api else "needs_external_adapter",
                        "course": "ready" if codex_ready else "needs_codex_runtime",
                    },
                    note="Returns official/open/borrow/preview/metadata links and never bypasses access controls.",
                ),
                "research_resource_workflow": _capability(
                    can_use_now=True,
                    status="ready",
                    mode="public_resource_read",
                    summary="ready" if codex_ready else "optional_needs_codex_runtime",
                    note="Reads verified public URLs; unverified URLs require explicit opt-in and access controls are never bypassed.",
                ),
                "research_compare_artifacts": _capability(
                    can_use_now=codex_ready,
                    status="ready" if codex_ready else "needs_setup",
                    missing=[] if codex_ready else ["openai-codex"],
                    setup_hint=None if codex_ready else "Install openai-codex and verify the local Codex runtime",
                    mode="saved_artifact_comparison",
                    note="Uses only project-local artifacts and validates source IDs structurally; citations remain source-level traceability, not independent fact verification.",
                ),
                "download_gallery": _capability(
                    can_use_now=gallery_ready,
                    status="ready" if gallery_ready else "needs_setup",
                    missing=[] if gallery_ready else ["gallery-dl"],
                    setup_hint=None if gallery_ready else status["gallery-dl"]["install_hint"],
                ),
            },
            "api_providers": api_providers,
            "optional_cli": status,
            "adapters": {
                "external_api_attached": bool(external_api),
                "local_search_attached": bool(search_tools),
                "ai_search_attached": bool(ai_search),
                "codex_runner_attached": bool(codex_runner),
            },
        }
    return _ok(
        data,
        optional_count=len(status),
        ready_capabilities=sum(
            1
            for capability in data["capabilities"].values()
            if capability["can_use_now"]
        ),
    )


def optional_tool_status() -> Dict[str, Dict[str, Any]]:
    optional_tools = {
        "gallery-dl": {
            "role": "image gallery and collection downloads",
            "install_hint": "uv tool install gallery-dl",
            "license_note": "GPL-2.0; compatible with Argus GPL distribution constraints",
        },
        "yt-dlp": {
            "role": "video/audio metadata and downloads",
            "install_hint": "uv tool install yt-dlp",
            "license_note": "Unlicense",
        },
        "scrapy": {
            "role": "large rule-based crawling projects",
            "install_hint": "uv tool install scrapy",
            "license_note": "BSD-3-Clause",
        },
        "crawl4ai": {
            "role": "LLM-friendly dynamic page crawling",
            "install_hint": "uv pip install crawl4ai && crawl4ai-setup",
            "license_note": "Apache-2.0",
            "python_module": "crawl4ai",
        },
        "openai-codex": {
            "role": "local Codex SDK research source",
            "install_hint": "uv pip install openai-codex",
            "license_note": "OpenAI SDK; used only when the runtime package is installed",
            "python_module": "openai_codex",
        },
    }

    status = {}
    for binary, info in optional_tools.items():
        path = shutil.which(binary)
        package_installed = bool(info.get("python_module") and importlib.util.find_spec(info["python_module"]))
        status[binary] = {
            **info,
            "installed": bool(path or package_installed),
            "path": path,
            "package_installed": package_installed,
        }
    return status


def web_search_provider_status() -> Dict[str, Dict[str, Any]]:
    providers = {
        "tavily": {
            "source": "web:tavily",
            "env_var": "TAVILY_API_KEY",
            "signup_url": "https://app.tavily.com/home",
            "role": "LLM-oriented web search",
        },
        "exa": {
            "source": "web:exa",
            "env_var": "EXA_API_KEY",
            "signup_url": "https://dashboard.exa.ai/",
            "role": "semantic web search",
        },
        "perplexity": {
            "source": "web:perplexity",
            "env_var": "PERPLEXITY_API_KEY",
            "signup_url": "https://www.perplexity.ai/settings/api",
            "role": "answer search with citations",
        },
        "brave": {
            "source": "web:brave",
            "env_var": "BRAVE_API_KEY",
            "signup_url": "https://api.search.brave.com/app/dashboard",
            "role": "independent web index",
        },
    }
    for provider in providers.values():
        provider["configured"] = bool(os.environ.get(provider["env_var"]))
        provider["status"] = "ready" if provider["configured"] else "needs_api_key"
        if not provider["configured"]:
            provider["setup_hint"] = f"Set {provider['env_var']}"
    return providers


def _capability(
    can_use_now: bool,
    status: str,
    missing: list[str] | None = None,
    setup_hint: str | None = None,
    **extra,
) -> Dict:
    payload = {
        "status": status,
        "can_use_now": can_use_now,
        "missing": missing or [],
    }
    if setup_hint:
        payload["setup_hint"] = setup_hint
    payload.update(extra)
    return payload


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}
