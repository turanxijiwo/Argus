"""
Research toolkit for agent-driven information gathering.

This module intentionally avoids new runtime dependencies. It provides a
stable MCP-facing surface for simple HTTP crawling, page image discovery,
cross-source research aggregation, and optional external CLI adapters.
"""

import os
from typing import Any, Dict, List, Optional

from .research_audio import search_openverse_audio
from .research_crawl import fetch_page_html, parse_page_html
from .research_batch import (
    DEFAULT_BATCH_OUTPUT_DIR,
    DEFAULT_BATCH_REPORT_PATH,
    build_research_batch_workflow,
)
from .research_gallery import download_gallery as run_gallery_download
from .research_health import toolkit_health as build_toolkit_health
from .research_images import build_research_images
from .research_pack import build_research_pack
from .research_page import (
    crawl_page_url,
    discover_page_images as build_discover_page_images,
)
from .research_probe import build_research_runtime_probe
from .research_render import format_crawl4ai_result
from .research_runtime import (
    MAX_HTML_BYTES,
    MAX_TEXT_CHARS,
    RETRIABLE_CRAWL_ERRORS,
    create_research_session,
    default_workflow_sources,
)
from .research_review import review_research_artifact
from .research_sources import run_source_search
from .research_source_ai import run_codex_search
from .research_topic import build_research_topic
from .research_workflow import (
    build_research_workflow,
    image_confidence as _image_confidence,
)


class ResearchToolkitTools:
    """High-level research and crawling tools for Codex/MCP clients."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        external_api: Optional[Any] = None,
        search_tools: Optional[Any] = None,
        article_reader: Optional[Any] = None,
        ai_search: Optional[Any] = None,
        codex_runner: Optional[Any] = None,
    ):
        self.project_root = os.path.abspath(project_root or os.getcwd())
        self.external_api = external_api
        self.search_tools = search_tools
        self.article_reader = article_reader
        self.ai_search = ai_search
        self.codex_runner = codex_runner
        self.session = create_research_session()

    def toolkit_health(self) -> Dict:
        return build_toolkit_health(
            external_api=self.external_api,
            search_tools=self.search_tools,
            ai_search=self.ai_search,
            codex_runner=self.codex_runner,
        )

    def crawl_url(
        self,
        url: str,
        render_js: bool = False,
        timeout: int = 20,
        max_chars: int = 12000,
    ) -> Dict:
        """Fetch one URL and extract title, text, links, and image candidates."""
        return crawl_page_url(
            url=url,
            render_js=render_js,
            timeout=timeout,
            max_chars=max_chars,
            fetch_html=self._fetch_html,
            parse_html=self._parse_html,
            max_text_chars=MAX_TEXT_CHARS,
        )

    def _format_crawl4ai_result(self, url: str, result: Any, max_chars: int) -> Dict:
        return format_crawl4ai_result(url=url, result=result, max_chars=max_chars)

    def discover_page_images(
        self,
        url: str,
        timeout: int = 20,
        limit: int = 100,
    ) -> Dict:
        """Extract normalized image URLs from a page without downloading files."""
        return build_discover_page_images(
            url=url,
            timeout=timeout,
            limit=limit,
            crawl_url=self.crawl_url,
        )

    def download_gallery(
        self,
        target: str,
        output_dir: str = "output/media",
        confirm: bool = False,
        timeout: int = 300,
    ) -> Dict:
        """
        Safe wrapper for gallery-dl.

        By default this returns the planned command only. It executes only when
        confirm=True and writes inside project_root.
        """
        return run_gallery_download(
            project_root=self.project_root,
            target=target,
            output_dir=output_dir,
            confirm=confirm,
            timeout=timeout,
        )

    def research_topic(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 10,
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
        return build_research_topic(
            query=query,
            sources=sources,
            limit=limit,
            run_source_search=self._run_source_search,
        )

    def research_images(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 5,
        images_per_page: int = 5,
        timeout: int = 20,
    ) -> Dict:
        """
        Search Openverse directly or discover image candidates from relevant pages.

        The default ``image:openverse`` source is anonymous and preserves
        creator/license metadata. Other sources keep the page-first workflow.
        """
        return build_research_images(
            query=query,
            sources=sources,
            limit=limit,
            images_per_page=images_per_page,
            timeout=timeout,
            research_topic=self.research_topic,
            discover_page_images=self.discover_page_images,
            image_confidence=_image_confidence,
        )

    def research_audio(
        self,
        query: str,
        limit: int = 5,
        timeout: int = 20,
    ) -> Dict:
        """Search Openverse for license-aware audio metadata without downloading media."""
        return search_openverse_audio(query=query, limit=limit, timeout=timeout)

    def research_pack(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 5,
        timeout: int = 20,
        max_chars_per_page: int = 4000,
    ) -> Dict:
        """
        Build a compact evidence packet by searching a topic and crawling page text.

        The whole packet remains successful when individual sources or pages fail;
        those failures are preserved in source_errors and each document entry.
        """
        return build_research_pack(
            query=query,
            sources=sources,
            limit=limit,
            timeout=timeout,
            max_chars_per_page=max_chars_per_page,
            research_topic=self.research_topic,
            crawl_url=self.crawl_url,
            max_text_chars=MAX_TEXT_CHARS,
        )

    def research_workflow(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        limit: int = 5,
        timeout: int = 20,
        max_chars_per_page: int = 4000,
        images_per_page: int = 5,
        render_js: bool = False,
        retries: int = 1,
        include_brief: bool = True,
        save: bool = False,
        save_brief: bool = True,
        output_dir: str = "output/research",
    ) -> Dict:
        """Run search, crawl, image extraction, brief rendering, and optional export."""
        sources = sources or default_workflow_sources(self.ai_search, self.codex_runner)
        return build_research_workflow(
            query=query,
            sources=sources,
            limit=limit,
            timeout=timeout,
            max_chars_per_page=max_chars_per_page,
            images_per_page=images_per_page,
            render_js=render_js,
            retries=retries,
            include_brief=include_brief,
            save=save,
            save_brief=save_brief,
            output_dir=output_dir,
            project_root=self.project_root,
            research_topic=self.research_topic,
            crawl_url=self.crawl_url,
            max_text_chars=MAX_TEXT_CHARS,
            retriable_errors=RETRIABLE_CRAWL_ERRORS,
        )

    def research_batch_workflow(
        self,
        queries: List[str],
        sources: Optional[List[str]] = None,
        limit: int = 5,
        timeout: int = 20,
        max_chars_per_page: int = 4000,
        images_per_page: int = 5,
        render_js: bool = False,
        retries: int = 1,
        output_dir: str = DEFAULT_BATCH_OUTPUT_DIR,
        report_path: str = DEFAULT_BATCH_REPORT_PATH,
    ) -> Dict:
        """Run saved research workflows for multiple queries and write a review report."""
        return build_research_batch_workflow(
            queries=queries,
            sources=sources or default_workflow_sources(self.ai_search, self.codex_runner),
            limit=limit,
            timeout=timeout,
            max_chars_per_page=max_chars_per_page,
            images_per_page=images_per_page,
            render_js=render_js,
            retries=retries,
            output_dir=output_dir,
            report_path=report_path,
            project_root=self.project_root,
            research_workflow=self.research_workflow,
        )

    def research_review_artifact(
        self, artifact_path: Optional[str] = None, handoff: Optional[Dict[str, Any]] = None, artifact_index: int = 0
    ) -> Dict:
        return review_research_artifact(
            artifact_path, self.project_root, handoff=handoff, artifact_index=artifact_index
        )
    def research_runtime_probe(
        self, adapters: Optional[List[str]] = None, url: str = "https://example.com",
        query: str = "OpenAI research toolkit", timeout: int = 30,
    ) -> Dict:
        return build_research_runtime_probe(
            adapters or ["crawl4ai", "codex"], url, query, timeout, self.crawl_url,
            lambda query, limit: run_codex_search(query, limit, self.codex_runner),
        )

    def _fetch_html(self, url: str, timeout: int) -> Dict:
        return fetch_page_html(self.session, url=url, timeout=timeout, max_html_bytes=MAX_HTML_BYTES)

    def _parse_html(self, html: str, base_url: str) -> Dict:
        return parse_page_html(html=html, base_url=base_url)

    def _run_source_search(self, source: str, query: str, limit: int) -> Dict:
        return run_source_search(
            source=source,
            query=query,
            limit=limit,
            external_api=self.external_api,
            search_tools=self.search_tools,
            ai_search=self.ai_search,
            codex_runner=self.codex_runner,
        )
