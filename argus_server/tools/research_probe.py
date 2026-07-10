"""Explicit runtime probes for optional Research Toolkit adapters."""

from typing import Any, Callable, Dict, Iterable, List


SUPPORTED_PROBES = {"crawl4ai", "codex"}


def build_research_runtime_probe(
    adapters: Iterable[str],
    url: str,
    query: str,
    timeout: int,
    crawl_url: Callable[..., Dict],
    codex_search: Callable[..., Dict],
) -> Dict:
    selected = _normalize_adapters(adapters)
    if not selected:
        return _err("adapters must include crawl4ai or codex", "INVALID_ADAPTERS")

    probes = {}
    for adapter in selected:
        if adapter == "crawl4ai":
            probes[adapter] = _probe_crawl4ai(url, timeout, crawl_url)
        else:
            probes[adapter] = _probe_codex(query, codex_search)
    verified_count = sum(1 for probe in probes.values() if probe.get("status") == "runtime_verified")
    return _ok(
        {"probes": probes},
        requested_adapters=selected,
        runtime_verified_count=verified_count,
        runtime_failed_count=len(probes) - verified_count,
    )


def _probe_crawl4ai(url: str, timeout: int, crawl_url: Callable[..., Dict]) -> Dict:
    result = crawl_url(url=url, render_js=True, timeout=timeout, max_chars=1000)
    if not result.get("success"):
        return _failed_probe("crawl4ai", result.get("error") or {})
    data = result.get("data") or {}
    return {
        "adapter": "crawl4ai",
        "status": "runtime_verified",
        "url": data.get("final_url") or url,
        "text_chars": len(data.get("text") or ""),
        "image_count": len(data.get("images") or []),
    }


def _probe_codex(query: str, codex_search: Callable[..., Dict]) -> Dict:
    result = codex_search(query=query, limit=1)
    if not result.get("success"):
        return _failed_probe("codex", result.get("error") or {})
    items = ((result.get("data") or {}).get("items") or [])
    if not items:
        return _failed_probe("codex", {"code": "EMPTY_RESULT", "message": "Codex returned no research items"})
    return {
        "adapter": "codex",
        "status": "runtime_verified",
        "result_count": len(items),
        "first_result_has_url": bool(items[0].get("url")),
    }


def _failed_probe(adapter: str, error: Dict[str, Any]) -> Dict:
    code = error.get("code") or "RUNTIME_ERROR"
    message = str(error.get("message") or "Optional runtime probe failed")
    if adapter == "codex" and ("failed to load configuration" in message or "unknown variant" in message):
        code = "CONFIG_ERROR"
        message = "Codex SDK could not load compatible user configuration"
    elif adapter == "codex" and ("read-only" in message.lower() or "permission" in message.lower()):
        code = "PERMISSION_ERROR"
        message = "Codex SDK could not access required user-level state"
    return {"adapter": adapter, "status": "runtime_failed", "error": {"code": code, "message": message}}


def _normalize_adapters(adapters: Iterable[str]) -> List[str]:
    selected = []
    for adapter in adapters or []:
        normalized = str(adapter or "").strip().lower()
        if normalized in SUPPORTED_PROBES and normalized not in selected:
            selected.append(normalized)
    return selected


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str) -> Dict:
    return {"success": False, "error": {"code": code, "message": message}}
