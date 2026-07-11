"""Resolve one bounded locator excerpt and verify its source content."""

import re
from typing import Any, Dict, Tuple

from .research_integrity import verify_document_fingerprint


MAX_EXCERPT_WORDS = 25


def resolve_locator_evidence(
    source: Dict,
    source_path: str,
    source_payload: Dict,
    locator: Dict,
    max_chars: int,
) -> Dict:
    locator_id = locator["locator_id"]
    document_index = locator.get("document_index")
    start_char = locator.get("start_char")
    end_char = locator.get("end_char")
    documents = source_payload.get("documents")
    if (
        not _is_int(document_index)
        or not isinstance(documents, list)
        or document_index < 0
        or document_index >= len(documents)
    ):
        return _stale_locator(locator_id, "invalid_document_index")
    document = documents[document_index]
    text = document.get("text") if isinstance(document, dict) else None
    if not isinstance(text, str):
        return _stale_locator(locator_id, "missing_document_text")

    integrity_result = verify_document_fingerprint(source, text, document_index)
    if not integrity_result.get("success"):
        integrity_result["error"]["locator_id"] = locator_id
        return integrity_result
    if (
        not _is_int(start_char)
        or not _is_int(end_char)
        or start_char < 0
        or end_char <= start_char
        or end_char > len(text)
    ):
        return _stale_locator(locator_id, "invalid_character_range")

    excerpt, truncated = _bounded_excerpt(text[start_char:end_char], max_chars)
    if not excerpt:
        return _stale_locator(locator_id, "empty_evidence")
    citation = source.get("citation") if isinstance(source.get("citation"), dict) else {}
    return _ok(
        {
            "locator_id": locator_id,
            "source_id": source["source_id"],
            "title": source.get("title") or source["source_id"],
            "artifact_path": source_path,
            "document_index": document_index,
            "paragraph_index": locator.get("paragraph_index"),
            "section": locator.get("section"),
            "page": locator.get("page"),
            "kind": locator.get("kind") or "paragraph",
            "start_char": start_char,
            "end_char": end_char,
            "excerpt": excerpt,
            "excerpt_chars": len(excerpt),
            "excerpt_words": len(excerpt.split()),
            "excerpt_truncated": truncated,
            "integrity": integrity_result["data"],
            "citation": citation,
        }
    )


def _bounded_excerpt(text: str, max_chars: int) -> Tuple[str, bool]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    words = cleaned.split()
    bounded = " ".join(words[:MAX_EXCERPT_WORDS])
    truncated = len(words) > MAX_EXCERPT_WORDS
    if len(bounded) > max_chars:
        bounded = bounded[:max_chars].rstrip()
        truncated = True
    return bounded, truncated


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _stale_locator(locator_id: str, reason: str) -> Dict:
    return _err(
        "Locator coordinates no longer resolve against the saved source artifact",
        "STALE_LOCATOR",
        locator_id=locator_id,
        reason=reason,
    )


def _ok(data: Any) -> Dict:
    return {"success": True, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
