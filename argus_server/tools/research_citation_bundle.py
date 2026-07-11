"""Build and save CSL-JSON and RIS bundles for comparison sources."""

import json
import os
from typing import Any, Dict, Iterable

from .research_io import research_artifact_filename, resolve_output_dir


def build_comparison_citation_bundle(sources: Iterable[Dict]) -> Dict:
    selected_sources = list(sources or [])
    if not selected_sources:
        return _err("At least one comparison source is required", "EMPTY_CITATION_BUNDLE")

    csl_items = []
    ris_records = []
    used_csl_ids = set()
    for source_index, source in enumerate(selected_sources):
        if not isinstance(source, dict):
            return _incomplete(source_index, None)
        source_id = str(source.get("source_id") or f"S{source_index + 1}")
        citation = source.get("citation")
        if not isinstance(citation, dict):
            return _incomplete(source_index, source_id)
        csl_json = citation.get("csl_json")
        ris = citation.get("ris")
        if not isinstance(csl_json, dict) or not isinstance(ris, str) or not ris.strip():
            return _incomplete(source_index, source_id)

        csl_item = dict(csl_json)
        csl_item["id"] = _unique_csl_id(csl_item.get("id"), source_id, used_csl_ids)
        csl_items.append(csl_item)
        ris_records.append(ris.strip())

    return _ok(
        {
            "csl_json": csl_items,
            "ris": "\n\n".join(ris_records) + "\n",
        },
        source_count=len(selected_sources),
        csl_item_count=len(csl_items),
        ris_record_count=len(ris_records),
    )


def save_comparison_citation_bundle(
    project_root: str,
    sources: Iterable[Dict],
    output_dir: str,
    query: str,
    timestamp: str,
) -> Dict:
    output_result = resolve_output_dir(project_root, output_dir)
    if not output_result.get("success"):
        return output_result
    bundle_result = build_comparison_citation_bundle(sources)
    if not bundle_result.get("success"):
        return bundle_result

    resolved_output = output_result["data"]["path"]
    csl_path = os.path.join(
        resolved_output,
        research_artifact_filename(query, timestamp, ".csl.json"),
    )
    ris_path = os.path.join(
        resolved_output,
        research_artifact_filename(query, timestamp, ".ris"),
    )
    bundle = bundle_result["data"]
    try:
        os.makedirs(resolved_output, exist_ok=True)
        with open(csl_path, "w", encoding="utf-8") as handle:
            json.dump(bundle["csl_json"], handle, ensure_ascii=False, indent=2)
        with open(ris_path, "w", encoding="utf-8") as handle:
            handle.write(bundle["ris"])
    except OSError:
        return _err(
            "Failed to write comparison citation bundle",
            "CITATION_BUNDLE_WRITE_ERROR",
        )

    return _ok(
        {
            "csl_json": {
                "format": "csl-json",
                "path": csl_path,
                "item_count": bundle_result["summary"]["csl_item_count"],
            },
            "ris": {
                "format": "ris",
                "path": ris_path,
                "record_count": bundle_result["summary"]["ris_record_count"],
            },
        },
        source_count=bundle_result["summary"]["source_count"],
    )


def _unique_csl_id(value: Any, source_id: str, used_ids: set) -> str:
    base_id = str(value or source_id.lower()).strip() or source_id.lower()
    candidate = base_id
    if candidate in used_ids:
        candidate = f"{base_id}-{source_id.lower()}"
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base_id}-{source_id.lower()}-{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _incomplete(source_index: int, source_id: Any) -> Dict:
    return _err(
        "Comparison source is missing CSL-JSON or RIS citation metadata",
        "INCOMPLETE_CITATION_METADATA",
        source_index=source_index,
        source_id=source_id,
    )


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
