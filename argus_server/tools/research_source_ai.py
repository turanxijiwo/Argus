"""Optional AI-backed source adapters for topic research."""

import importlib.util
import json
import os
import re
from typing import Any, Dict, List, Optional

from .research_web import clean_text, is_http_url


WEB_SEARCH_SOURCES = ["web", "web:tavily", "web:exa", "web:perplexity", "web:brave"]
WEB_SEARCH_PROVIDERS = ("tavily", "exa", "perplexity", "brave")


def run_web_search(source: str, query: str, limit: int, ai_search: Optional[Any] = None) -> Dict:
    provider = "tavily"
    if ":" in source:
        provider = source.split(":", 1)[1].strip().lower()
    if provider not in WEB_SEARCH_PROVIDERS:
        return _err(
            f"Unsupported web search provider: {provider}",
            code="UNSUPPORTED_SOURCE",
            supported=WEB_SEARCH_SOURCES,
        )
    if not ai_search:
        return _err("AI web search adapter is unavailable", code="ADAPTER_UNAVAILABLE")

    result = ai_search.ai_web_search(
        query=query,
        provider=provider,
        max_results=limit,
        include_answer=True,
        search_depth="basic",
    )
    if not result.get("success"):
        return result
    items = normalize_web_search(source, provider, query, result)
    return _ok({"items": items}, count=len(items), provider=provider)


def normalize_web_search(source: str, provider: str, query: str, result: Dict) -> List[Dict]:
    data = result.get("data") or {}
    items = []

    answer = data.get("answer")
    if answer:
        items.append(
            {
                "source": source,
                "title": f"{provider} answer: {query}",
                "url": None,
                "snippet": answer,
                "score": 1.0,
                "raw": {"provider": provider, "answer": answer},
            }
        )

    for index, item in enumerate(data.get("results") or []):
        url = item.get("url")
        title = item.get("title") or url or f"{provider} result {index + 1}"
        items.append(
            {
                "source": source,
                "title": title,
                "url": url,
                "snippet": item.get("content") or item.get("description") or item.get("text"),
                "score": _score_or_default(item.get("score"), 0.5),
                "raw": item,
            }
        )

    for index, citation in enumerate(data.get("citations") or []):
        if isinstance(citation, str):
            url = citation
            title = citation
        elif isinstance(citation, dict):
            url = citation.get("url")
            title = citation.get("title") or url
        else:
            url = None
            title = None
        items.append(
            {
                "source": source,
                "title": title or f"{provider} citation {index + 1}",
                "url": url,
                "snippet": answer,
                "score": max(0.1, 0.5 - index * 0.01),
                "raw": citation,
            }
        )

    return items


def run_codex_search(query: str, limit: int, codex_runner: Optional[Any] = None) -> Dict:
    if codex_runner:
        try:
            payload = codex_runner(query=query, limit=limit)
        except Exception as ex:
            return _err(f"Codex runner failed: {ex}", code="CODEX_RUNNER_ERROR")
        result = normalize_codex_search_payload(payload, query=query, limit=limit)
        if result.get("success"):
            result["summary"]["runner"] = "injected"
        return result

    if importlib.util.find_spec("openai_codex") is None:
        return _err(
            "OpenAI Codex SDK is not installed",
            code="NOT_INSTALLED",
            install_hint="uv pip install openai-codex",
            source="codex",
        )

    try:
        from openai_codex import Codex, Sandbox
    except ImportError as ex:
        return _err(f"OpenAI Codex SDK import failed: {ex}", code="IMPORT_ERROR")

    model = os.environ.get("ARGUS_CODEX_MODEL") or "gpt-5.4"
    prompt = _codex_research_prompt(query=query, limit=limit)
    try:
        with Codex() as codex:
            thread = codex.thread_start(model=model, sandbox=Sandbox.read_only)
            run_result = thread.run(prompt)
    except Exception as ex:
        return _err(f"OpenAI Codex SDK research failed: {ex}", code="CODEX_SDK_ERROR", model=model)

    payload = getattr(run_result, "final_response", run_result)
    result = normalize_codex_search_payload(payload, query=query, limit=limit)
    if result.get("success"):
        result["summary"]["runner"] = "openai_codex"
        result["summary"]["model"] = model
    return result


def normalize_codex_search_payload(payload: Any, query: str, limit: int) -> Dict:
    parsed = payload
    if isinstance(payload, str):
        parsed = _extract_json_payload(payload)
        if parsed is None:
            return _err(
                "Codex SDK response did not contain valid JSON",
                code="PARSE_ERROR",
                raw_excerpt=payload[:1000],
            )
    elif isinstance(payload, dict) and "success" in payload and "data" in payload:
        if not payload.get("success"):
            return payload
        parsed = payload.get("data") or {}

    if isinstance(parsed, dict):
        candidates = parsed.get("items") or []
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        return _err("Codex SDK response must be a JSON object or list", code="PARSE_ERROR")

    items = []
    for index, item in enumerate(candidates[:limit]):
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link")
        if url is not None:
            url = str(url).strip()
            if url and not is_http_url(url):
                continue
        title = clean_text(str(item.get("title") or url or f"Codex result {index + 1}"))
        snippet = clean_text(
            str(
                item.get("snippet")
                or item.get("summary")
                or item.get("content")
                or item.get("description")
                or ""
            )
        )
        items.append(
            {
                "source": "codex",
                "title": title,
                "url": url or None,
                "snippet": snippet,
                "score": _score_or_default(item.get("score"), max(0.1, 0.9 - index * 0.05)),
                "raw": item,
            }
        )

    return _ok({"items": items}, count=len(items), query=query)


def _score_or_default(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _codex_research_prompt(query: str, limit: int) -> str:
    return (
        "You are helping Argus perform personal, non-commercial research.\n"
        "Find public web pages relevant to the query and return only JSON.\n"
        f"Query: {json.dumps(query, ensure_ascii=False)}\n"
        f"Limit: {limit}\n"
        'Schema: {"items":[{"title":"...","url":"https://...","snippet":"short summary","score":0.0}]}\n'
        "Rules: include direct URLs, keep snippets short, do not include copyrighted full text, "
        "and do not add prose outside the JSON object."
    )


def _extract_json_payload(text: str) -> Optional[Any]:
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start == -1 or end == -1 or end <= start:
            continue
        try:
            return json.loads(candidate[start:end + 1])
        except json.JSONDecodeError:
            continue
    return None


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_SOURCE_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
