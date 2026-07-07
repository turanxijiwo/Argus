"""Cross-source topic research aggregation for Argus."""

from typing import Any, Callable, Dict, List, Optional

from .research_web import clean_text


RunSourceSearchFn = Callable[[str, str, int], Dict]


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_TOOLKIT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


def _safe_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def build_research_topic(
    query: str,
    sources: Optional[List[str]],
    limit: int,
    run_source_search: RunSourceSearchFn,
) -> Dict:
    """
    Search a topic across normalized information sources.

    Supported source names:
    - local_news
    - hackernews
    - wikipedia
    - reddit:<subreddit>, for example reddit:LocalLLaMA
    - github_code
    - web or web:<provider>, where provider is tavily, exa, perplexity, or brave
    - codex, using the optional local OpenAI Codex SDK
    """
    query = clean_text(query)
    if not query:
        return _err("query cannot be empty", code="INVALID_QUERY")

    limit = _safe_int(limit, 10, 1, 50)
    selected_sources = sources or ["local_news", "hackernews", "wikipedia"]
    normalized = []
    source_results = {}

    for source in selected_sources:
        source_name = str(source or "").strip()
        result = run_source_search(source_name, query, limit)
        source_results[source_name] = result
        if result.get("success"):
            normalized.extend(result.get("data", {}).get("items", []))

    normalized.sort(key=lambda item: item.get("score", 0), reverse=True)
    return _ok(
        {
            "query": query,
            "sources": source_results,
            "merged": normalized[: limit * max(1, len(selected_sources))],
        },
        source_count=len(selected_sources),
        merged_count=len(normalized),
    )
