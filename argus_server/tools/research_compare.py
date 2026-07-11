"""Compare saved Research Toolkit artifacts with source-level citations."""

import json
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

from .research_codex_summary import run_secure_codex_json
from .research_compare_brief import render_comparison_brief
from .research_compare_contract import (
    COMPARISON_DEVELOPER_INSTRUCTIONS,
    MAX_SOURCE_CHARS,
    MAX_TOTAL_SOURCE_CHARS,
    build_comparison_prompt,
    build_comparison_source,
    normalize_comparison_payload,
    public_comparison_source,
)
from .research_handoff import build_comparison_handoff
from .research_io import (
    resolve_output_dir,
    resolve_project_path,
    save_research_brief_artifact,
    save_research_json_artifact,
    utc_timestamp_for_filename,
)
from .research_web import clean_text


MIN_COMPARISON_SOURCES = 2
MAX_COMPARISON_SOURCES = 6
DEFAULT_COMPARISON_OUTPUT_DIR = "output/research/comparisons"


class ResearchComparisonTools:
    """Create a traceable comparison from saved research artifacts."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        comparison_runner: Optional[Callable[..., Any]] = None,
    ):
        self.project_root = os.path.realpath(os.path.abspath(project_root or os.getcwd()))
        self.comparison_runner = comparison_runner

    def research_compare_artifacts(
        self,
        artifact_paths: Iterable[str],
        focus: Optional[str] = None,
        target_language: str = "zh-CN",
        max_claims: int = 5,
        save: bool = False,
        save_brief: bool = True,
        output_dir: str = DEFAULT_COMPARISON_OUTPUT_DIR,
    ) -> Dict:
        selected_paths = _normalize_paths(artifact_paths)
        if len(selected_paths) < MIN_COMPARISON_SOURCES:
            return _err(
                "At least two research artifact paths are required",
                "NOT_ENOUGH_ARTIFACTS",
            )
        if len(selected_paths) > MAX_COMPARISON_SOURCES:
            return _err(
                f"No more than {MAX_COMPARISON_SOURCES} artifacts can be compared",
                "TOO_MANY_ARTIFACTS",
            )

        selected_output_dir = output_dir or DEFAULT_COMPARISON_OUTPUT_DIR
        if save:
            output_result = resolve_output_dir(self.project_root, selected_output_dir)
            if not output_result.get("success"):
                return output_result

        loaded_result = self._load_artifacts(selected_paths)
        if not loaded_result.get("success"):
            return loaded_result
        loaded_artifacts = loaded_result["data"]
        if len(loaded_artifacts) < MIN_COMPARISON_SOURCES:
            return _err(
                "At least two unique research artifacts are required",
                "NOT_ENOUGH_UNIQUE_ARTIFACTS",
            )

        max_claims = _safe_int(max_claims, 5, 1, 10)
        selected_focus = clean_text(focus) or "Compare selected research resources"
        selected_language = clean_text(target_language) or "zh-CN"
        per_source_chars = min(
            MAX_SOURCE_CHARS,
            MAX_TOTAL_SOURCE_CHARS // len(loaded_artifacts),
        )
        sources = []
        for index, artifact in enumerate(loaded_artifacts, 1):
            source_result = build_comparison_source(
                payload=artifact["payload"],
                artifact_path=artifact["path"],
                source_id=f"S{index}",
                max_chars=per_source_chars,
            )
            if not source_result.get("success"):
                source_result["error"]["artifact_index"] = index - 1
                return source_result
            sources.append(source_result["data"])

        comparison_result = self._run_comparison(
            sources=sources,
            focus=selected_focus,
            target_language=selected_language,
            max_claims=max_claims,
        )
        if not comparison_result.get("success"):
            return comparison_result
        comparison = comparison_result["data"]
        report = {
            "query": selected_focus,
            "artifact_paths": [source["artifact_path"] for source in sources],
            "sources": [public_comparison_source(source) for source in sources],
            "source_errors": [],
            "comparison": comparison,
            "artifact": None,
            "brief": None,
        }
        report["brief"] = render_comparison_brief(report)

        if save:
            timestamp = utc_timestamp_for_filename()
            if save_brief:
                brief_result = save_research_brief_artifact(
                    project_root=self.project_root,
                    workflow=report,
                    output_dir=selected_output_dir,
                    query=f"comparison-{selected_focus}",
                    timestamp=timestamp,
                )
                if not brief_result.get("success"):
                    return brief_result
            artifact_result = save_research_json_artifact(
                project_root=self.project_root,
                workflow=report,
                output_dir=selected_output_dir,
                query=f"comparison-{selected_focus}",
                timestamp=timestamp,
            )
            if not artifact_result.get("success"):
                return artifact_result

        report["handoff"] = build_comparison_handoff(
            report=report,
            project_root=self.project_root,
            output_dir=selected_output_dir if save else "",
            entrypoint="mcp",
        )
        return _ok(
            report,
            source_count=len(sources),
            claim_count=comparison["claim_count"],
            citation_count=comparison["citation_count"],
            saved=bool(report.get("artifact")),
            handoff_schema=report["handoff"]["schema"],
        )

    def _load_artifacts(self, paths: List[str]) -> Dict:
        loaded = []
        seen = set()
        root = os.path.realpath(self.project_root)
        for index, path in enumerate(paths):
            resolved = resolve_project_path(path, root)
            if not resolved:
                return _err(
                    "artifact_path must point inside the Argus project",
                    "UNSAFE_ARTIFACT_PATH",
                    artifact_index=index,
                )
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                with open(resolved, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                return _err(
                    "Failed to read research artifact",
                    "ARTIFACT_READ_ERROR",
                    artifact_index=index,
                )
            if not isinstance(payload, dict):
                return _err(
                    "Research artifact must contain a JSON object",
                    "INVALID_ARTIFACT",
                    artifact_index=index,
                )
            loaded.append(
                {
                    "path": os.path.relpath(resolved, root),
                    "payload": payload,
                }
            )
        return _ok(loaded)

    def _run_comparison(
        self,
        sources: List[Dict],
        focus: str,
        target_language: str,
        max_claims: int,
    ) -> Dict:
        if self.comparison_runner:
            try:
                payload = self.comparison_runner(
                    sources=sources,
                    focus=focus,
                    target_language=target_language,
                    max_claims=max_claims,
                )
            except Exception:
                return _err("Codex comparison runner failed", "CODEX_RUNNER_ERROR")
            runner = "injected"
            model = None
        else:
            prompt = build_comparison_prompt(
                sources=sources,
                focus=focus,
                target_language=target_language,
                max_claims=max_claims,
            )
            runtime_result = run_secure_codex_json(
                prompt,
                COMPARISON_DEVELOPER_INSTRUCTIONS,
            )
            if not runtime_result.get("success"):
                return runtime_result
            payload = runtime_result.get("data")
            runner = runtime_result["summary"]["runner"]
            model = runtime_result["summary"]["model"]

        normalized = normalize_comparison_payload(
            payload=payload,
            source_ids=[source["source_id"] for source in sources],
            max_claims=max_claims,
            focus=focus,
        )
        if not normalized.get("success"):
            return normalized
        normalized["data"].update(
            {
                "method": "codex",
                "runner": runner,
                "model": model,
            }
        )
        return normalized


def _normalize_paths(paths: Iterable[str]) -> List[str]:
    if isinstance(paths, str):
        paths = [paths]
    return [str(path).strip() for path in (paths or []) if str(path).strip()]


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
