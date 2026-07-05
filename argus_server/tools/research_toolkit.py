"""
Research toolkit for agent-driven information gathering.

This module intentionally avoids new runtime dependencies. It provides a
stable MCP-facing surface for simple HTTP crawling, page image discovery,
cross-source research aggregation, and optional external CLI adapters.
"""

import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) ArgusResearch/1.0 Safari/537.36"
)

_MAX_HTML_BYTES = 3 * 1024 * 1024
_MAX_TEXT_CHARS = 20000


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_TOOLKIT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _safe_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


class _PageParser(HTMLParser):
    """Small dependency-free HTML extractor for title, text, links, and images."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.meta_description = ""
        self.links: List[Dict[str, str]] = []
        self.images: List[Dict[str, str]] = []
        self._in_title = False
        self._skip_depth = 0
        self._current_anchor: Optional[Dict[str, str]] = None
        self._text_chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        attrs_dict = {str(k).lower(): v for k, v in attrs if k}
        tag = tag.lower()

        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1
            return

        if tag == "title":
            self._in_title = True
            return

        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in ("description", "og:description") and attrs_dict.get("content"):
                self.meta_description = str(attrs_dict["content"]).strip()
            return

        if tag == "a" and attrs_dict.get("href"):
            self._current_anchor = {
                "url": urljoin(self.base_url, str(attrs_dict["href"])),
                "text": "",
            }
            return

        if tag in ("img", "source"):
            self._add_image(attrs_dict)

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in ("script", "style", "noscript") and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if tag == "a" and self._current_anchor:
            if _is_http_url(self._current_anchor["url"]):
                self._current_anchor["text"] = _clean_text(self._current_anchor["text"])[:300]
                self.links.append(self._current_anchor)
            self._current_anchor = None

    def handle_data(self, data: str):
        if not data or self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        if self._current_anchor is not None:
            self._current_anchor["text"] += data
        self._text_chunks.append(data)

    def _add_image(self, attrs: Dict[str, str]):
        candidates = []
        for key in ("src", "data-src", "data-original"):
            if attrs.get(key):
                candidates.append(str(attrs[key]))
        if attrs.get("srcset"):
            candidates.extend(_parse_srcset(str(attrs["srcset"])))

        seen = set()
        for candidate in candidates:
            image_url = urljoin(self.base_url, candidate.strip())
            if not _is_http_url(image_url) or image_url in seen:
                continue
            seen.add(image_url)
            self.images.append(
                {
                    "url": image_url,
                    "alt": str(attrs.get("alt") or "").strip(),
                    "width": str(attrs.get("width") or "").strip(),
                    "height": str(attrs.get("height") or "").strip(),
                }
            )

    def text(self) -> str:
        return _clean_text(" ".join(self._text_chunks))


def _parse_srcset(srcset: str) -> List[str]:
    candidates = []
    for item in srcset.split(","):
        part = item.strip().split()
        if part:
            candidates.append(part[0])
    return candidates


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class ResearchToolkitTools:
    """High-level research and crawling tools for Codex/MCP clients."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        external_api: Optional[Any] = None,
        search_tools: Optional[Any] = None,
        article_reader: Optional[Any] = None,
    ):
        self.project_root = os.path.abspath(project_root or os.getcwd())
        self.external_api = external_api
        self.search_tools = search_tools
        self.article_reader = article_reader
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": _DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    # ───────────────────────── Capability map ─────────────────────────
    def toolkit_health(self) -> Dict:
        """Return built-in capabilities and optional high-quality CLI adapters."""
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
                "install_hint": "uv tool install crawl4ai",
                "license_note": "Apache-2.0",
            },
        }

        status = {}
        for binary, info in optional_tools.items():
            path = shutil.which(binary)
            status[binary] = {
                **info,
                "installed": bool(path),
                "path": path,
            }

        return _ok(
            {
                "built_in": {
                    "crawl_url": "HTTP HTML fetch + text/link/image extraction",
                    "discover_page_images": "image candidate extraction from HTML",
                    "research_topic": "cross-source normalized research aggregation",
                    "download_gallery": "safe gallery-dl wrapper when installed",
                },
                "optional_cli": status,
            },
            optional_count=len(status),
        )

    # ───────────────────────── HTTP crawling ─────────────────────────
    def crawl_url(
        self,
        url: str,
        render_js: bool = False,
        timeout: int = 20,
        max_chars: int = 12000,
    ) -> Dict:
        """Fetch one URL and extract title, text, links, and image candidates."""
        if not _is_http_url(url):
            return _err(
                f"Invalid URL: {url}",
                code="INVALID_URL",
                suggestion="URL must start with http:// or https://",
            )
        if render_js:
            return _err(
                "JavaScript rendering is not available in the dependency-free adapter",
                code="RENDER_JS_UNSUPPORTED",
                suggestion="Install and enable a Crawl4AI adapter in the next integration phase",
            )

        timeout = _safe_int(timeout, 20, 3, 90)
        max_chars = _safe_int(max_chars, 12000, 500, _MAX_TEXT_CHARS)
        fetched = self._fetch_html(url, timeout=timeout)
        if not fetched.get("success"):
            return fetched

        parsed = self._parse_html(fetched["data"]["html"], fetched["data"]["final_url"])
        text = parsed["text"][:max_chars]
        return _ok(
            {
                "url": url,
                "final_url": fetched["data"]["final_url"],
                "status_code": fetched["data"]["status_code"],
                "content_type": fetched["data"]["content_type"],
                "title": parsed["title"],
                "description": parsed["description"],
                "text": text,
                "text_truncated": len(parsed["text"]) > len(text),
                "links": parsed["links"][:100],
                "images": parsed["images"][:100],
            },
            source="http",
            link_count=len(parsed["links"]),
            image_count=len(parsed["images"]),
            text_chars=len(text),
        )

    def discover_page_images(
        self,
        url: str,
        timeout: int = 20,
        limit: int = 100,
    ) -> Dict:
        """Extract normalized image URLs from a page without downloading files."""
        limit = _safe_int(limit, 100, 1, 300)
        result = self.crawl_url(url=url, render_js=False, timeout=timeout, max_chars=500)
        if not result.get("success"):
            return result
        images = result["data"]["images"][:limit]
        return _ok(
            {
                "page_url": result["data"]["final_url"],
                "title": result["data"]["title"],
                "images": images,
            },
            source="page_images",
            count=len(images),
            requested_limit=limit,
        )

    # ───────────────────────── Optional media CLI ─────────────────────────
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
        binary = shutil.which("gallery-dl")
        if not binary:
            return _err(
                "gallery-dl is not installed",
                code="NOT_INSTALLED",
                install_hint="uv tool install gallery-dl",
            )
        if not target:
            return _err("target cannot be empty", code="INVALID_TARGET")

        resolved_output = self._resolve_output_dir(output_dir)
        if not resolved_output.get("success"):
            return resolved_output

        command = [binary, target]
        plan = {
            "command": command,
            "cwd": resolved_output["data"]["path"],
            "target": target,
            "confirm_required": not confirm,
        }
        if not confirm:
            return _ok(
                plan,
                mode="dry_run",
                note="Set confirm=True to run gallery-dl inside the project output directory",
            )

        os.makedirs(resolved_output["data"]["path"], exist_ok=True)
        timeout = _safe_int(timeout, 300, 30, 1800)
        try:
            completed = subprocess.run(
                command,
                cwd=resolved_output["data"]["path"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return _err("gallery-dl timed out", code="TIMEOUT", timeout=timeout)
        except Exception as ex:
            return _err(f"gallery-dl failed to start: {ex}", code="EXEC_ERROR")

        return _ok(
            {
                **plan,
                "returncode": completed.returncode,
                "stdout": (completed.stdout or "")[-5000:],
                "stderr": (completed.stderr or "")[-5000:],
            },
            mode="executed",
            success_exit=completed.returncode == 0,
        )

    # ───────────────────────── Cross-source research ─────────────────────────
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
        """
        query = _clean_text(query)
        if not query:
            return _err("query cannot be empty", code="INVALID_QUERY")

        limit = _safe_int(limit, 10, 1, 50)
        sources = sources or ["local_news", "hackernews", "wikipedia"]
        normalized = []
        source_results = {}

        for source in sources:
            source_name = str(source or "").strip()
            result = self._run_source_search(source_name, query, limit)
            source_results[source_name] = result
            if result.get("success"):
                normalized.extend(result.get("data", {}).get("items", []))

        normalized.sort(key=lambda item: item.get("score", 0), reverse=True)
        return _ok(
            {
                "query": query,
                "sources": source_results,
                "merged": normalized[: limit * max(1, len(sources))],
            },
            source_count=len(sources),
            merged_count=len(normalized),
        )

    # ───────────────────────── Internal helpers ─────────────────────────
    def _fetch_html(self, url: str, timeout: int) -> Dict:
        try:
            response = self.session.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) > _MAX_HTML_BYTES:
                    return _err(
                        "HTML response is too large",
                        code="RESPONSE_TOO_LARGE",
                        max_bytes=_MAX_HTML_BYTES,
                    )
            encoding = response.encoding or response.apparent_encoding or "utf-8"
            html = bytes(content).decode(encoding, errors="replace")
            return _ok(
                {
                    "html": html,
                    "final_url": response.url,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                },
                bytes=len(content),
            )
        except requests.Timeout:
            return _err("Request timed out", code="TIMEOUT", url=url)
        except requests.RequestException as ex:
            return _err(f"Request failed: {ex}", code="NETWORK_ERROR", url=url)

    def _parse_html(self, html: str, base_url: str) -> Dict:
        parser = _PageParser(base_url)
        parser.feed(html or "")
        title = _clean_text(parser.title)
        return {
            "title": title,
            "description": parser.meta_description,
            "text": parser.text(),
            "links": _dedupe_by_url(parser.links),
            "images": _dedupe_by_url(parser.images),
        }

    def _resolve_output_dir(self, output_dir: str) -> Dict:
        if not output_dir:
            output_dir = "output/media"
        path = output_dir
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)
        path = os.path.abspath(path)
        if os.path.commonpath([self.project_root, path]) != self.project_root:
            return _err(
                "output_dir must stay inside the Argus project directory",
                code="UNSAFE_OUTPUT_DIR",
                project_root=self.project_root,
            )
        return _ok({"path": path})

    def _run_source_search(self, source: str, query: str, limit: int) -> Dict:
        if source == "local_news":
            if not self.search_tools:
                return _err("local news search adapter is unavailable", code="ADAPTER_UNAVAILABLE")
            result = self.search_tools.search_news_unified(
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
            if not self.external_api:
                return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
            result = self.external_api.search_hackernews(query=query, hits=limit)
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
            if not self.external_api:
                return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
            result = self.external_api.search_wikipedia(query=query, limit=limit)
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

        if source.startswith("reddit:"):
            if not self.external_api:
                return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
            subreddit = source.split(":", 1)[1].strip()
            if not subreddit:
                return _err("reddit source must include subreddit, e.g. reddit:LocalLLaMA", code="INVALID_SOURCE")
            result = self.external_api.search_reddit(
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
            if not self.external_api:
                return _err("external API adapter is unavailable", code="ADAPTER_UNAVAILABLE")
            result = self.external_api.search_github_code(query=query, limit=limit)
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
            supported=["local_news", "hackernews", "wikipedia", "reddit:<subreddit>", "github_code"],
        )


def _dedupe_by_url(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped = []
    for item in items:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped
