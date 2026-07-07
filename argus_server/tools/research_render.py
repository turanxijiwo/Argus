"""Optional JavaScript rendering adapters for Argus research crawling."""

import asyncio
import importlib.util
from typing import Any, Dict

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

    async def run_crawl():
        browser_config = BrowserConfig()
        run_config = CrawlerRunConfig()
        async with AsyncWebCrawler(config=browser_config) as crawler:
            return await asyncio.wait_for(
                crawler.arun(url=url, config=run_config),
                timeout=timeout,
            )

    try:
        result = asyncio.run(run_crawl())
    except asyncio.TimeoutError:
        return _err("Crawl4AI crawl timed out", code="TIMEOUT", timeout=timeout)
    except Exception as ex:
        return _err(f"Crawl4AI crawl failed: {ex}", code="CRAWL4AI_ERROR")

    return format_crawl4ai_result(url=url, result=result, max_chars=max_chars)


def _err(message: str, code: str = "RESEARCH_RENDER_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
