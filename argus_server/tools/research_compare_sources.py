"""Citation metadata and evidence locators for saved research artifacts."""

import re
from typing import Any, Dict, List, Optional, Tuple

from .research_citation import build_citation_metadata


MAX_SOURCE_CHARS = 8000
MAX_TOTAL_SOURCE_CHARS = 40000
MAX_LOCATOR_CHARS = 700
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
PAGE_PATTERN = re.compile(
    r"^(?:page|p\.?|页)\s*[:#]?\s*(\d+)(?:\s*(?:of|/)\s*\d+)?$",
    re.IGNORECASE,
)


def build_comparison_source(
    payload: Dict,
    artifact_path: str,
    source_id: str,
    max_chars: int,
) -> Dict:
    documents = [
        (index, document)
        for index, document in enumerate(payload.get("documents") or [])
        if document.get("success") and str(document.get("text") or "").strip()
    ]
    if not documents:
        return _err(
            "Research artifact has no readable evidence text",
            "NO_READABLE_EVIDENCE",
        )

    resource = payload.get("resource") or {}
    first_document = documents[0][1]
    title = _clean_text(
        resource.get("title")
        or first_document.get("page_title")
        or first_document.get("title")
        or payload.get("query")
        or source_id
    )
    url = (
        (payload.get("selection") or {}).get("url")
        or first_document.get("final_url")
        or first_document.get("url")
        or resource.get("landing_page_url")
    )
    authors = resource.get("creators") or resource.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    selected_authors = [_clean_text(author) for author in authors if _clean_text(author)]

    remaining = max(1, int(max_chars))
    selected_texts = []
    locators = []
    input_chars = 0
    input_truncated = False
    for document_index, document in documents:
        raw_text = str(document.get("text") or "")
        if remaining <= 0:
            input_truncated = True
            break
        selected_text = raw_text[:remaining]
        selected_texts.append(selected_text)
        input_chars += len(selected_text)
        document_locators = build_evidence_locators(
            text=selected_text,
            source_id=source_id,
            document_index=document_index,
            start_number=len(locators) + 1,
        )
        locators.extend(document_locators)
        remaining -= len(selected_text)
        input_truncated = input_truncated or len(raw_text) > len(selected_text)
        input_truncated = input_truncated or bool(document.get("text_truncated"))

    summary = payload.get("summary") or {}
    summary_text = summary.get("summary") if isinstance(summary, dict) else ""
    resource_type = payload.get("resource_type") or resource.get("resource_type")
    citation = build_citation_metadata(
        resource=resource,
        title=title,
        authors=selected_authors,
        url=url,
        resource_type=resource_type,
        source_id=source_id,
    )
    return _ok(
        {
            "source_id": source_id,
            "artifact_path": artifact_path,
            "title": title,
            "url": url,
            "resource_type": resource_type,
            "authors": selected_authors,
            "citation": citation,
            "summary": _clean_text(summary_text),
            "text": "\n\n".join(selected_texts),
            "locators": locators,
            "locator_count": len(locators),
            "input_chars": input_chars,
            "input_truncated": input_truncated,
            "document_count": len(documents),
        }
    )


def build_evidence_locators(
    text: str,
    source_id: str,
    document_index: int,
    start_number: int = 1,
) -> List[Dict]:
    spans: List[Tuple[int, int, int, Optional[str], Optional[int]]] = []
    current_section = None
    current_page = None
    paragraph_start = None
    paragraph_end = None
    paragraph_index = 0
    offset = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_start, paragraph_end, paragraph_index
        if paragraph_start is None or paragraph_end is None:
            return
        paragraph_index += 1
        for chunk_start, chunk_end in _split_span(text, paragraph_start, paragraph_end):
            spans.append(
                (
                    chunk_start,
                    chunk_end,
                    paragraph_index,
                    current_section,
                    current_page,
                )
            )
        paragraph_start = None
        paragraph_end = None

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        heading_match = HEADING_PATTERN.match(stripped)
        page_match = PAGE_PATTERN.match(stripped)
        if heading_match:
            flush_paragraph()
            current_section = _clean_text(heading_match.group(1)) or current_section
        elif page_match:
            flush_paragraph()
            current_page = int(page_match.group(1))
        elif stripped:
            if paragraph_start is None:
                leading = len(line) - len(line.lstrip())
                paragraph_start = offset + leading
            paragraph_end = offset + len(line.rstrip())
        else:
            flush_paragraph()
        offset += len(line)
    flush_paragraph()

    if not spans and text.strip():
        start = len(text) - len(text.lstrip())
        end = len(text.rstrip())
        spans = [(start, end, 1, current_section, current_page)]

    locators = []
    for locator_offset, (start, end, paragraph, section, page) in enumerate(spans):
        locator_id = f"{source_id}:L{start_number + locator_offset}"
        locators.append(
            {
                "locator_id": locator_id,
                "document_index": document_index,
                "paragraph_index": paragraph,
                "section": section,
                "page": page,
                "kind": "page" if page is not None else "section" if section else "paragraph",
                "start_char": start,
                "end_char": end,
                "text": text[start:end],
            }
        )
    return locators


def public_comparison_source(source: Dict) -> Dict:
    public_source = {
        key: value
        for key, value in source.items()
        if key not in {"text", "summary", "locators"}
    }
    public_source["locators"] = [
        {key: value for key, value in locator.items() if key != "text"}
        for locator in source.get("locators") or []
    ]
    return public_source


def _split_span(text: str, start: int, end: int) -> List[Tuple[int, int]]:
    chunks = []
    cursor = start
    while cursor < end:
        while cursor < end and text[cursor].isspace():
            cursor += 1
        if cursor >= end:
            break
        chunk_end = min(cursor + MAX_LOCATOR_CHARS, end)
        if chunk_end < end:
            boundary = text.rfind(" ", cursor + MAX_LOCATOR_CHARS // 2, chunk_end)
            if boundary > cursor:
                chunk_end = boundary
        while chunk_end > cursor and text[chunk_end - 1].isspace():
            chunk_end -= 1
        if chunk_end <= cursor:
            chunk_end = min(cursor + MAX_LOCATOR_CHARS, end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _ok(data: Any) -> Dict:
    return {"success": True, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
