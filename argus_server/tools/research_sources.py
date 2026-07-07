"""Source adapters and normalization for Argus topic research."""

import importlib.util
import json
import os
import re
from typing import Any, Dict, List, Optional

from .research_web import clean_text, is_http_url


SUPPORTED_SOURCES = [
    "local_news",
    "hackernews",
    "wikipedia",
    "reddit:<subreddit>",
    "github_code",
    "web",
    "web:<tavily|exa|perplexity|brave>",
    "codex",
]


def run_source_search(
    source: str,
    query: str,
    limit: int,
    external_api: Optional[Any] = None,
    search_tools: Optional[Any] = None,
    ai_search: Optional[Any] = None,
    codex_runner: Optional[Any] = None,
) -> Dict:
    if source == "local_news":
        if not search_tools:
            return _err("local news search adapter is unavailable", code="ADAPTER_UNAVAILABLE")
        result = search_tools.search_news_unified(
            query=query,
            limit=limit,
            include_url=True,
            include_rss=True,
            rss_limit=limit,
        )
        items = []
        for item in result.get("data") or []:
            items.append(
                {
                    "source": "local_news",
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": item.get("content") or item.get("summary"),
                    "score": item.get("similarity_score", 0),
                    "raw": item,
                }
            )
        for item in result.get("rss") or []:
            items.append(
                {
                    "source": "rss",
                    "title": item.get("title"),
                    "url": item.get("link") or item.get("url"),
                    "snippet": item.get("summary"),
                    "score": 0.5,
                    "raw": item,
                }
            )
        return _ok({"items": items}, count=len(items))

    if source == "hackernews":
        if not external_api:
            return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
        result = external_api.search_hackernews(query=query, hits=limit)
        hits = ((result.get("data") or {}).get("hits") or []) if result.get("success") else []
        return _ok(
            {
                "items": [
                    {
                        "source": "hackernews",
                        "title": item.get("title"),
                        "url": item.get("url") or item.get("hn_url"),
                        "snippet": item.get("comment_text"),
                        "score": item.get("points") or 0,
                        "raw": item,
                    }
                    for item in hits
                ]
            },
            count=len(hits),
        ) if result.get("success") else result

    if source == "wikipedia":
        if not external_api:
            return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
        result = external_api.search_wikipedia(query=query, limit=limit)
        articles = ((result.get("data") or {}).get("articles") or []) if result.get("success") else []
        return _ok(
            {
                "items": [
                    {
                        "source": "wikipedia",
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "snippet": item.get("snippet"),
                        "score": item.get("wordcount") or 0,
                        "raw": item,
                    }
                    for item in articles
                ]
            },
            count=len(articles),
        ) if result.get("success") else result

    if source == "web" or source.startswith("web:"):
        provider = "tavily"
        if ":" in source:
            provider = source.split(":", 1)[1].strip().lower()
        if provider not in ("tavily", "exa", "perplexity", "brave"):
            return _err(
                f"Unsupported web search provider: {provider}",
                code="UNSUPPORTED_SOURCE",
                supported=["web", "web:tavily", "web:exa", "web:perplexity", "web:brave"],
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

    if source == "codex":
        return run_codex_search(query=query, limit=limit, codex_runner=codex_runner)

    if source.startswith("reddit:"):
        if not external_api:
            return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
        subreddit = source.split(":", 1)[1].strip()
        if not subreddit:
            return _err("reddit source must include subreddit, e.g. reddit:LocalLLaMA", code="INVALID_SOURCE")
        result = external_api.search_reddit(
            subreddit=subreddit,
            sort="top",
            time_filter="month",
            limit=limit,
        )
        posts = ((result.get("data") or {}).get("posts") or []) if result.get("success") else []
        filtered = [post for post in posts if query.lower() in (post.get("title") or "").lower()]
        selected = filtered or posts
        return _ok(
            {
                "items": [
                    {
                        "source": source,
                        "title": item.get("title"),
                        "url": item.get("url") or item.get("permalink"),
                        "snippet": item.get("selftext"),
                        "score": item.get("score") or 0,
                        "raw": item,
                    }
                    for item in selected[:limit]
                ]
            },
            count=len(selected[:limit]),
        ) if result.get("success") else result

    if source == "github_code":
        if not external_api:
            return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
        result = external_api.search_github_code(query=query, limit=limit)
        results = ((result.get("data") or {}).get("results") or []) if result.get("success") else []
        return _ok(
            {
                "items": [
                    {
                        "source": "github_code",
                        "title": f"{item.get('repo')}:{item.get('path')}",
                        "url": item.get("url"),
                        "snippet": item.get("name"),
                        "score": item.get("score") or 0,
                        "raw": item,
                    }
                    for item in results
                ]
            },
            count=len(results),
        ) if result.get("success") else result

    return _err(
        f"Unsupported source: {source}",
        code="UNSUPPORTED_SOURCE",
        supported=SUPPORTED_SOURCES,
    )


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


def page_candidate_items(topic_data: Dict, merged_items: List[Dict]) -> List[Dict]:
    items = []
    seen = set()

    def add_item(item: Any):
        if not isinstance(item, dict):
            return
        key = (
            str(item.get("source") or ""),
            str(item.get("url") or ""),
            str(item.get("title") or ""),
            str(item.get("snippet") or ""),
        )
        if key in seen:
            return
        seen.add(key)
        items.append(item)

    for item in merged_items or []:
        add_item(item)

    for result in (topic_data.get("sources") or {}).values():
        if not isinstance(result, dict) or not result.get("success"):
            continue
        for item in ((result.get("data") or {}).get("items") or []):
            add_item(item)

    return items


def page_candidates(items: List[Dict], limit: int) -> List[Dict]:
    candidates = []
    seen = set()
    for item in items:
        url = item.get("url")
        if not is_http_url(url) or url in seen:
            continue
        seen.add(url)
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return candidates


def source_errors(sources: Dict[str, Dict]) -> List[Dict[str, Any]]:
    errors = []
    for source_name, result in sources.items():
        if result.get("success"):
            continue
        error = result.get("error") or {}
        errors.append(
            {
                "source": source_name,
                "code": error.get("code"),
                "message": error.get("message"),
            }
        )
    return errors


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
