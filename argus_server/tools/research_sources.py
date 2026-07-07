"""Source adapters and normalization for Argus topic research."""

from typing import Any, Dict, List, Optional

from .research_source_ai import run_codex_search, run_web_search
from .research_web import is_http_url


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
        return run_web_search(source=source, query=query, limit=limit, ai_search=ai_search)

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


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_SOURCE_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
