"""Project-local artifact writing for research workflows."""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def save_research_json_artifact(
    project_root: str,
    workflow: Dict,
    output_dir: str,
    query: str,
    timestamp: Optional[str] = None,
) -> Dict:
    resolved_output = resolve_output_dir(project_root, output_dir)
    if not resolved_output.get("success"):
        return resolved_output

    timestamp = timestamp or utc_timestamp_for_filename()
    filename = f"research-{_slugify_filename(query)}-{timestamp}.json"
    path = os.path.join(resolved_output["data"]["path"], filename)
    workflow["artifact"] = {
        "format": "json",
        "path": path,
    }

    try:
        os.makedirs(resolved_output["data"]["path"], exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(workflow, handle, ensure_ascii=False, indent=2, default=str)
    except OSError as ex:
        workflow["artifact"] = None
        return _err(f"Failed to write research workflow artifact: {ex}", code="WRITE_ERROR")

    return _ok(workflow["artifact"], path=path)


def save_research_brief_artifact(
    project_root: str,
    workflow: Dict,
    output_dir: str,
    query: str,
    timestamp: Optional[str] = None,
) -> Dict:
    resolved_output = resolve_output_dir(project_root, output_dir)
    if not resolved_output.get("success"):
        return resolved_output

    brief = workflow.get("brief") or {}
    content = brief.get("content") or ""
    if not content:
        return _err("Research brief content is empty", code="EMPTY_BRIEF")

    timestamp = timestamp or utc_timestamp_for_filename()
    filename = f"research-{_slugify_filename(query)}-{timestamp}.md"
    path = os.path.join(resolved_output["data"]["path"], filename)
    brief["artifact"] = {
        "format": "markdown",
        "path": path,
    }
    workflow["brief"] = brief

    try:
        os.makedirs(resolved_output["data"]["path"], exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as ex:
        brief["artifact"] = None
        return _err(f"Failed to write research brief artifact: {ex}", code="WRITE_ERROR")

    return _ok(brief["artifact"], path=path)


def resolve_output_dir(project_root: str, output_dir: str) -> Dict:
    if not output_dir:
        output_dir = "output/research"
    path = output_dir
    if not os.path.isabs(path):
        path = os.path.join(project_root, path)
    path = os.path.abspath(path)
    project_root = os.path.abspath(project_root)
    if os.path.commonpath([project_root, path]) != project_root:
        return _err(
            "output_dir must stay inside the Argus project directory",
            code="UNSAFE_OUTPUT_DIR",
            project_root=project_root,
        )
    return _ok({"path": path})


def utc_timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value or "").strip("-._")
    return (slug or "research")[:80]


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_IO_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
