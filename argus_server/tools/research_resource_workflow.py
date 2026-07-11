"""Read, summarize, and save one discovered research resource."""

import os
from typing import Any, Callable, Dict, Optional

from .research_brief import render_research_brief
from .research_codex_summary import run_codex_summary
from .research_handoff import build_workflow_handoff
from .research_io import (
    resolve_output_dir,
    save_research_brief_artifact,
    save_research_json_artifact,
    utc_timestamp_for_filename,
)
from .research_resource_content import (
    resource_document,
    select_readable_resource_url,
    selected_sources,
    validate_resource_access,
)
from .research_web import clean_text


class ResearchResourceWorkflowTools:
    """Turn one resource-search result into a standard research artifact."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        resource_search: Optional[Callable[..., Dict]] = None,
        article_reader: Optional[Any] = None,
        summary_runner: Optional[Callable[..., Any]] = None,
    ):
        self.project_root = os.path.abspath(project_root or os.getcwd())
        self.resource_search = resource_search
        self.article_reader = article_reader
        self.summary_runner = summary_runner

    def research_resource_workflow(
        self,
        query: str,
        resource_type: str,
        resource_index: int = 0,
        institution: Optional[str] = None,
        language: Optional[str] = None,
        access: str = "open",
        limit: int = 5,
        timeout: int = 30,
        max_chars: int = 30000,
        summarize: bool = True,
        target_language: str = "zh-CN",
        summary_points: int = 5,
        allow_unverified: bool = False,
        include_brief: bool = True,
        save: bool = False,
        save_brief: bool = True,
        output_dir: str = "output/research/resources",
    ) -> Dict:
        query = clean_text(query)
        if not query:
            return _err("query cannot be empty", "INVALID_QUERY")
        if not self.resource_search:
            return _err("resource search adapter is unavailable", "ADAPTER_UNAVAILABLE")
        if not self.article_reader:
            return _err("article reader adapter is unavailable", "ADAPTER_UNAVAILABLE")

        selected_output_dir = output_dir or "output/research/resources"
        if save:
            output_result = resolve_output_dir(self.project_root, selected_output_dir)
            if not output_result.get("success"):
                return output_result
        resource_index_result = _resource_index(resource_index)
        if not resource_index_result.get("success"):
            return resource_index_result
        selected_index = resource_index_result["data"]["index"]
        limit = _safe_int(limit, 5, 1, 25)
        timeout = _safe_int(timeout, 30, 5, 90)
        max_chars = _safe_int(max_chars, 30000, 1000, 100000)
        summary_points = _safe_int(summary_points, 5, 1, 10)

        search_result = self.resource_search(
            query=query,
            resource_type=resource_type,
            institution=institution,
            language=language,
            access=access,
            limit=limit,
            timeout=timeout,
        )
        if not search_result.get("success"):
            return search_result
        search_data = search_result.get("data") or {}
        resources = search_data.get("resources") or []
        if not resources:
            return _err(
                "No research resources matched the requested filters",
                "NO_RESOURCE_RESULTS",
                source_errors=search_data.get("source_errors") or [],
            )
        if selected_index >= len(resources):
            return _err(
                "resource_index is outside the available result range",
                "RESOURCE_INDEX_OUT_OF_RANGE",
                resource_index=selected_index,
                resource_count=len(resources),
            )

        selected_resource = resources[selected_index]
        access_error = validate_resource_access(
            selected_resource, allow_unverified=bool(allow_unverified)
        )
        if access_error:
            return access_error
        selection = select_readable_resource_url(selected_resource)
        if not selection:
            return _err(
                "Selected resource has no publicly readable URL",
                "NO_READABLE_URL",
            )

        read_result = self.article_reader.read_article(
            url=selection["url"],
            timeout=timeout,
        )
        document = resource_document(
            query=query,
            resource=selected_resource,
            selection=selection,
            read_result=read_result,
            max_chars=max_chars,
        )
        source_errors = list(search_data.get("source_errors") or [])
        summary_data = None
        summary_error = None
        if summarize and document.get("success"):
            summary_result = run_codex_summary(
                text=document.get("text") or "",
                title=selected_resource.get("title") or query,
                target_language=target_language,
                max_points=summary_points,
                summary_runner=self.summary_runner,
            )
            if summary_result.get("success"):
                summary_data = summary_result.get("data")
            else:
                summary_error = summary_result.get("error") or {}
                source_errors.append(
                    {
                        "source": "codex_summary",
                        "code": summary_error.get("code"),
                        "message": summary_error.get("message"),
                    }
                )

        workflow = {
            "query": query,
            "resource_type": resource_type,
            "sources": selected_sources(selected_resource, source_errors),
            "merged": resources,
            "source_errors": source_errors,
            "documents": [document],
            "images": [],
            "artifact": None,
            "brief": None,
            "resource": selected_resource,
            "selection": {"resource_index": selected_index, **selection},
            "summary": summary_data,
            "summary_error": summary_error,
        }
        if include_brief or (save and save_brief):
            workflow["brief"] = render_research_brief(workflow)

        if save:
            timestamp = utc_timestamp_for_filename()
            if save_brief and workflow.get("brief"):
                brief_result = save_research_brief_artifact(
                    project_root=self.project_root,
                    workflow=workflow,
                    output_dir=selected_output_dir,
                    query=f"{resource_type}-{query}",
                    timestamp=timestamp,
                )
                if not brief_result.get("success"):
                    return brief_result
            artifact_result = save_research_json_artifact(
                project_root=self.project_root,
                workflow=workflow,
                output_dir=selected_output_dir,
                query=f"{resource_type}-{query}",
                timestamp=timestamp,
            )
            if not artifact_result.get("success"):
                return artifact_result

        workflow["handoff"] = build_workflow_handoff(
            workflow=workflow,
            project_root=self.project_root,
            output_dir=selected_output_dir if save else "",
            entrypoint="mcp_resource",
        )
        return _ok(
            workflow,
            resource_count=len(resources),
            selected_resource_index=selected_index,
            selected_access=selected_resource.get("access"),
            read_success=bool(document.get("success")),
            summary_requested=bool(summarize),
            summary_success=bool(summary_data),
            source_error_count=len(source_errors),
            brief_included=bool(workflow.get("brief")),
            saved=bool(workflow.get("artifact")),
            handoff_schema=workflow["handoff"]["schema"],
        )


def _resource_index(value: Any) -> Dict:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return _err("resource_index must be an integer", "INVALID_RESOURCE_INDEX")
    if index < 0:
        return _err("resource_index cannot be negative", "INVALID_RESOURCE_INDEX")
    return _ok({"index": index})


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
