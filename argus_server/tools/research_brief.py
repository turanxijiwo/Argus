"""Markdown rendering for Argus research workflows."""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse


def render_research_brief(workflow: Dict) -> Dict:
    query = workflow.get("query") or "Research"
    documents = workflow.get("documents") or []
    images = workflow.get("images") or []
    source_errors = workflow.get("source_errors") or []
    summary = workflow.get("summary") or {}
    successful_documents = [document for document in documents if document.get("success")]
    failed_documents = [document for document in documents if not document.get("success")]
    generated_at = _utc_iso_timestamp()

    lines = [
        "---",
        "type: argus-research-brief",
        f"query: {json.dumps(query, ensure_ascii=False)}",
        f"generated_at: {generated_at}",
        f"documents: {len(documents)}",
        f"successful_documents: {len(successful_documents)}",
        f"images: {len(images)}",
        f"source_errors: {len(source_errors)}",
        "tags: [argus, research-brief]",
        "---",
        "",
        f"# Research Brief: {query}",
        "",
        f"> {len(successful_documents)} usable pages, {len(failed_documents)} page errors, {len(images)} image candidates.",
        "",
    ]

    if source_errors:
        lines.extend(["## Source Errors", ""])
        for error in source_errors:
            code = error.get("code") or "UNKNOWN"
            message = error.get("message") or ""
            lines.append(f"- `{error.get('source')}`: `{code}` {message}".rstrip())
        lines.append("")

    if summary.get("summary"):
        lines.extend(["## Summary", ""])
        lines.append(_clip_markdown_text(summary.get("summary"), 4000))
        lines.append("")
        for point in (summary.get("key_points") or [])[:10]:
            lines.append(f"- {_clip_markdown_text(point, 600)}")
        if summary.get("key_points"):
            lines.append("")

    if successful_documents:
        lines.extend(["## Key Sources", ""])
        for index, document in enumerate(successful_documents[:8], 1):
            title = document.get("page_title") or document.get("title") or document.get("url") or f"Source {index}"
            url = document.get("final_url") or document.get("url")
            lines.append(f"### {index}. {_markdown_link(title, url)}")
            lines.append("")
            meta = [
                f"source: `{document.get('source') or 'unknown'}`",
                f"status: `{document.get('status_code') or 'n/a'}`",
                f"attempts: `{document.get('crawl_attempts') or 1}`",
            ]
            lines.append("- " + " · ".join(meta))
            if document.get("snippet"):
                lines.append(f"- Search snippet: {_clip_markdown_text(document.get('snippet'), 220)}")
            if document.get("description"):
                lines.append(f"- Page description: {_clip_markdown_text(document.get('description'), 220)}")
            excerpt = _clip_markdown_text(document.get("text"), 500)
            if excerpt:
                lines.append("")
                lines.append(excerpt)
            links = [link for link in (document.get("links") or []) if link.get("url")][:3]
            if links:
                lines.append("")
                lines.append("Related links:")
                for link in links:
                    label = link.get("text") or link.get("url")
                    lines.append(f"- {_markdown_link(label, link.get('url'))}")
            lines.append("")

    if images:
        lines.extend(["## Image Candidates", ""])
        for image in images[:10]:
            label = image.get("alt") or image.get("image_url") or "image"
            page_title = image.get("source_page_title") or image.get("source_page_url") or "source page"
            if image.get("license"):
                license_label = " ".join(
                    part for part in [image.get("license"), image.get("license_version")] if part
                )
                details = [f"license {_markdown_link(license_label, image.get('license_url'))}"]
                if image.get("provider"):
                    details.append(f"provider `{image.get('provider')}`")
                lines.append(
                    f"- {_markdown_link(label, image.get('image_url'))} "
                    f"from {_markdown_link(page_title, image.get('source_page_url'))} "
                    f"({' · '.join(details)})"
                )
                if image.get("attribution"):
                    lines.append(f"  - Attribution: {_clip_markdown_text(image.get('attribution'), 300)}")
                if image.get("license_verification_required"):
                    lines.append("  - Verify license metadata and attribution requirements before use.")
            else:
                lines.append(
                    f"- {_markdown_link(label, image.get('image_url'))} "
                    f"from {_markdown_link(page_title, image.get('source_page_url'))} "
                    f"(confidence {image.get('confidence')})"
                )
        lines.append("")

    if failed_documents:
        lines.extend(["## Page Errors", ""])
        for document in failed_documents:
            error = document.get("error") or {}
            code = error.get("code") or "UNKNOWN"
            message = error.get("message") or ""
            lines.append(
                f"- {_markdown_link(document.get('title') or document.get('url'), document.get('url'))}: "
                f"`{code}` {message}".rstrip()
            )
        lines.append("")

    lines.extend(["---", "_Generated by Argus research_workflow._"])
    content = "\n".join(lines)
    return {
        "format": "markdown",
        "content": content,
        "artifact": None,
        "document_count": len(documents),
        "successful_document_count": len(successful_documents),
        "image_count": len(images),
        "source_error_count": len(source_errors),
    }


def _utc_iso_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clip_markdown_text(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _markdown_link(label: Any, url: Any) -> str:
    clean_label = re.sub(r"\s+", " ", str(label or url or "untitled")).strip()
    clean_label = clean_label.replace("[", "\\[").replace("]", "\\]")
    clean_url = str(url or "").strip()
    if _is_http_url(clean_url):
        return f"[{clean_label}]({clean_url})"
    return clean_label


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
