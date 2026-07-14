"""HTTP and HTML helpers for Argus research tools."""

import re
from html.parser import HTMLParser
from typing import Any, Dict, List
from urllib.parse import urljoin

from .research_network import is_http_url


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_html(html: str, base_url: str) -> Dict:
    parser = _PageParser(base_url)
    parser.feed(html or "")
    title = clean_text(parser.title)
    return {
        "title": title,
        "description": parser.meta_description,
        "text": parser.text(),
        "links": dedupe_by_url(parser.links),
        "images": dedupe_by_url(parser.images),
    }


def format_crawl4ai_result(url: str, result: Any, max_chars: int) -> Dict:
    if not getattr(result, "success", False):
        return _err(
            getattr(result, "error_message", None) or "Crawl4AI crawl failed",
            code="CRAWL4AI_ERROR",
            status_code=getattr(result, "status_code", None),
        )

    final_url = getattr(result, "url", None) or url
    html = getattr(result, "cleaned_html", None) or getattr(result, "html", "") or ""
    parsed = parse_html(html, final_url)
    markdown_text = _markdown_to_text(getattr(result, "markdown", None))
    text_source = markdown_text or parsed["text"]
    text = text_source[:max_chars]

    links = _normalize_crawl4ai_links(getattr(result, "links", {}) or {})
    images = _normalize_crawl4ai_images(getattr(result, "media", {}) or {}, final_url)
    metadata = getattr(result, "metadata", None) or {}
    response_headers = getattr(result, "response_headers", None) or {}

    return _ok(
        {
            "url": url,
            "final_url": final_url,
            "status_code": getattr(result, "redirected_status_code", None) or getattr(result, "status_code", None),
            "content_type": response_headers.get("content-type", ""),
            "title": metadata.get("title") or parsed["title"],
            "description": metadata.get("description") or parsed["description"],
            "text": text,
            "text_truncated": len(text_source) > len(text),
            "links": (links or parsed["links"])[:100],
            "images": (images or parsed["images"])[:100],
        },
        source="crawl4ai",
        link_count=len(links or parsed["links"]),
        image_count=len(images or parsed["images"]),
        text_chars=len(text),
    )


def dedupe_by_url(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped = []
    for item in items:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
    return deduped


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
        self._current_anchor: Dict[str, str] | None = None
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
            if is_http_url(self._current_anchor["url"]):
                self._current_anchor["text"] = clean_text(self._current_anchor["text"])[:300]
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
            if not is_http_url(image_url) or image_url in seen:
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
        return clean_text(" ".join(self._text_chunks))


def _parse_srcset(srcset: str) -> List[str]:
    candidates = []
    for item in srcset.split(","):
        part = item.strip().split()
        if part:
            candidates.append(part[0])
    return candidates


def _markdown_to_text(markdown: Any) -> str:
    if not markdown:
        return ""
    if isinstance(markdown, str):
        return clean_text(markdown)
    for attr in ("fit_markdown", "raw_markdown", "markdown_with_citations"):
        value = getattr(markdown, attr, None)
        if value:
            return clean_text(str(value))
    return clean_text(str(markdown))


def _normalize_crawl4ai_links(links: Dict[str, List[Dict]]) -> List[Dict[str, str]]:
    normalized = []
    for group in ("internal", "external"):
        for item in links.get(group, []) or []:
            url = item.get("href") or item.get("url")
            if not url:
                continue
            normalized.append(
                {
                    "url": url,
                    "text": clean_text(item.get("text") or item.get("title") or "")[:300],
                }
            )
    return dedupe_by_url(normalized)


def _normalize_crawl4ai_images(media: Dict[str, List[Dict]], base_url: str) -> List[Dict[str, str]]:
    images = []
    for item in media.get("images", []) or []:
        image_url = item.get("src") or item.get("url")
        if not image_url:
            continue
        image_url = urljoin(base_url, str(image_url))
        if not is_http_url(image_url):
            continue
        images.append(
            {
                "url": image_url,
                "alt": str(item.get("alt") or item.get("title") or "").strip(),
                "width": str(item.get("width") or "").strip(),
                "height": str(item.get("height") or "").strip(),
            }
        )
    return dedupe_by_url(images)


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_WEB_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
