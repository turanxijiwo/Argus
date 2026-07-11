"""Content fingerprints for comparison inputs and locator replay."""

import hashlib
import re
from typing import Any, Dict, Iterable, Tuple


CONTENT_FINGERPRINT_ALGORITHM = "sha256"
CONTENT_FINGERPRINT_SCOPE = "comparison_input_v1"


def build_content_fingerprint(documents: Iterable[Tuple[int, str]]) -> Dict:
    return {
        "algorithm": CONTENT_FINGERPRINT_ALGORITHM,
        "scope": CONTENT_FINGERPRINT_SCOPE,
        "documents": [
            {
                "document_index": document_index,
                "text_chars": len(text),
                "sha256": _sha256(text),
            }
            for document_index, text in documents
        ],
    }


def verify_document_fingerprint(source: Dict, text: str, document_index: int) -> Dict:
    fingerprint = source.get("content_fingerprint")
    if fingerprint is None:
        return _ok({"status": "unverified", "reason": "missing_content_fingerprint"})
    source_id = source.get("source_id")
    if not isinstance(fingerprint, dict):
        return _invalid(source_id, document_index, "fingerprint_not_object")
    if fingerprint.get("algorithm") != CONTENT_FINGERPRINT_ALGORITHM:
        return _invalid(source_id, document_index, "unsupported_algorithm")
    if fingerprint.get("scope") != CONTENT_FINGERPRINT_SCOPE:
        return _invalid(source_id, document_index, "unsupported_scope")
    documents = fingerprint.get("documents")
    if not isinstance(documents, list):
        return _invalid(source_id, document_index, "documents_not_list")
    matches = [
        item
        for item in documents
        if isinstance(item, dict)
        and _is_int(item.get("document_index"))
        and item["document_index"] == document_index
    ]
    if len(matches) != 1:
        return _invalid(source_id, document_index, "missing_or_duplicate_document")
    document = matches[0]
    text_chars = document.get("text_chars")
    expected_sha256 = document.get("sha256")
    if not _is_int(text_chars) or text_chars < 0:
        return _invalid(source_id, document_index, "invalid_text_chars")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        return _invalid(source_id, document_index, "invalid_sha256")
    observed_sha256 = _sha256(text[:text_chars]) if len(text) >= text_chars else None
    if observed_sha256 != expected_sha256:
        return _err(
            "Saved source content no longer matches the comparison fingerprint",
            "SOURCE_CONTENT_MISMATCH",
            source_id=source_id,
            document_index=document_index,
        )
    return _ok(
        {
            "status": "verified",
            "algorithm": CONTENT_FINGERPRINT_ALGORITHM,
            "scope": CONTENT_FINGERPRINT_SCOPE,
            "text_chars": text_chars,
            "sha256": expected_sha256,
        }
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _invalid(source_id: Any, document_index: int, reason: str) -> Dict:
    return _err(
        "Comparison artifact contains invalid content fingerprint metadata",
        "INVALID_CONTENT_FINGERPRINT",
        source_id=source_id,
        document_index=document_index,
        reason=reason,
    )


def _ok(data: Any) -> Dict:
    return {"success": True, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
