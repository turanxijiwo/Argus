"""Optional JavaScript rendering adapters for Argus research crawling."""

import asyncio
import importlib.util
from typing import Any, Dict

from .research_network import is_http_url, validate_public_http_url
from .research_web import format_crawl4ai_result


def crawl_url_with_crawl4ai(url: str, timeout: int, max_chars: int) -> Dict:
    if importlib.util.find_spec("crawl4ai") is None:
        return _err(
            "Crawl4AI is not installed",
            code="NOT_INSTALLED",
            install_hint="uv pip install crawl4ai && crawl4ai-setup",
        )

    try:
        from crawl4ai import AsyncWebCrawler
        from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
    except ImportError as ex:
        return _err(f"Crawl4AI import failed: {ex}", code="IMPORT_ERROR")

    initial_validation = validate_public_http_url(url)
    if not initial_validation.get("success"):
        return initial_validation

    async def run_crawl():
        browser_config = BrowserConfig()
        run_config = CrawlerRunConfig()
        guard_state: Dict[str, Dict] = {}
        crawler = AsyncWebCrawler(config=browser_config)

        async def install_guard(page, **kwargs):
            await _install_public_network_guard(page, guard_state)

        crawler.crawler_strategy.set_hook("on_page_context_created", install_guard)
        try:
            async with crawler:
                result = await asyncio.wait_for(
                    crawler.arun(url=url, config=run_config),
                    timeout=timeout,
                )
        except Exception:
            if guard_state.get("blocked_result"):
                return None, guard_state["blocked_result"]
            raise
        return result, guard_state.get("blocked_result")

    try:
        result, blocked_result = asyncio.run(run_crawl())
    except asyncio.TimeoutError:
        return _err("Crawl4AI crawl timed out", code="TIMEOUT", timeout=timeout)
    except Exception as ex:
        return _err(f"Crawl4AI crawl failed: {ex}", code="CRAWL4AI_ERROR")

    if blocked_result:
        return blocked_result
    return format_crawl4ai_result(url=url, result=result, max_chars=max_chars)


async def _install_public_network_guard(page: Any, guard_state: Dict[str, Dict]) -> None:
    async def guard_request(route: Any) -> None:
        request_url = route.request.url
        if not is_http_url(request_url):
            await route.continue_()
            return

        validation = await asyncio.to_thread(validate_public_http_url, request_url)
        if not validation.get("success"):
            guard_state.setdefault("blocked_result", validation)
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    await page.route("**/*", guard_request)


def _err(message: str, code: str = "RESEARCH_RENDER_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
