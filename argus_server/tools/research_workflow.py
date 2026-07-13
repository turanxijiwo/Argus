"""One-call research workflow orchestration for Argus topic research."""

import re
from typing import Any, Callable, Dict, Iterable, List

from .research_brief import render_research_brief
from .research_crawl import crawl_page_with_retries
from .research_io import (
    resolve_output_dir,
    save_research_brief_artifact,
    save_research_json_artifact,
    utc_timestamp_for_filename,
)
from .research_handoff import build_workflow_handoff
from .research_images import (
    OPENVERSE_SOURCE,
    _compact_source_result,
    search_openverse_images,
)
from .research_sources import (
    page_candidate_items,
    page_candidates,
    source_errors,
)
from .research_web import clean_text


ResearchTopicFn = Callable[..., Dict]
CrawlUrlFn = Callable[..., Dict]


def build_research_workflow(
    query: str,
    sources: List[str],
    limit: int,
    timeout: int,
    max_chars_per_page: int,
    images_per_page: int,
    render_js: bool,
    retries: int,
    include_brief: bool,
    save: bool,
    save_brief: bool,
    output_dir: str,
    project_root: str,
    research_topic: ResearchTopicFn,
    crawl_url: CrawlUrlFn,
    max_text_chars: int,
    retriable_errors: Iterable[str],
) -> Dict:
    """
    Run the full research loop: search, crawl, extract images, and render a brief.

    Page-level failures stay in documents[].error so a partial workflow can still
    return useful evidence. Hard failures are limited to invalid input and unsafe
    or unwritable export paths.
    """
    query = clean_text(query)
    if not query:
        return _err("query cannot be empty", code="INVALID_QUERY")

    limit = _safe_int(limit, 5, 1, 20)
    timeout = _safe_int(timeout, 20, 3, 90)
    max_chars_per_page = _safe_int(max_chars_per_page, 4000, 500, max_text_chars)
    images_per_page = _safe_int(images_per_page, 5, 0, 30)
    retries = _safe_int(retries, 1, 0, 3)
    selected_sources = sources or []
    page_sources = [source for source in selected_sources if source != OPENVERSE_SOURCE]
    selected_output_dir = output_dir or "output/research"
    if save:
        resolved_output = resolve_output_dir(project_root, selected_output_dir)
        if not resolved_output.get("success"):
            return resolved_output

    topic_data = {}
    if page_sources:
        topic_result = research_topic(query=query, sources=page_sources, limit=limit)
        if not topic_result.get("success"):
            return topic_result
        topic_data = topic_result.get("data") or {}
    merged_items = topic_data.get("merged") or []
    candidate_pages = page_candidates(page_candidate_items(topic_data, merged_items), limit)
    source_results = dict(topic_data.get("sources") or {})
    documents = []
    images = []
    page_images = []
    seen_images = set()
    crawl_cache = {}

    if OPENVERSE_SOURCE in selected_sources:
        openverse_result = search_openverse_images(query=query, limit=limit, timeout=timeout)
        source_results[OPENVERSE_SOURCE] = _compact_source_result(openverse_result)
        if openverse_result.get("success"):
            for image in (openverse_result.get("data") or {}).get("images") or []:
                image_url = image.get("image_url")
                if not image_url or image_url in seen_images:
                    continue
                seen_images.add(image_url)
                images.append(image)

    errors_by_source = source_errors(source_results)
    for page in candidate_pages:
        page_url = page["url"]
        if page_url not in crawl_cache:
            crawl_cache[page_url] = crawl_page_with_retries(
                crawl_url_func=crawl_url,
                url=page_url,
                render_js=bool(render_js),
                timeout=timeout,
                max_chars=max_chars_per_page,
                retries=retries,
                retriable_errors=retriable_errors,
            )
        crawl_result, attempt_count = crawl_cache[page_url]
        document = workflow_document_from_crawl(
            query=query,
            page=page,
            crawl_result=crawl_result,
            attempt_count=attempt_count,
        )
        documents.append(document)

        if not document.get("success") or images_per_page <= 0:
            continue
        for image in (document.get("images") or [])[:images_per_page]:
            image_url = image.get("url")
            if not image_url or image_url in seen_images:
                continue
            seen_images.add(image_url)
            page_images.append(
                {
                    "query": query,
                    "image_url": image_url,
                    "alt": image.get("alt", ""),
                    "width": image.get("width", ""),
                    "height": image.get("height", ""),
                    "source": page.get("source"),
                    "source_page_url": page_url,
                    "source_page_title": document.get("page_title") or page.get("title"),
                    "source_page_snippet": page.get("snippet"),
                    "confidence": image_confidence(query, page, image),
                }
            )

    page_images.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    images.extend(page_images)
    crawl_error_count = sum(1 for item in documents if not item.get("success"))
    skipped_item_count = max(0, len(merged_items) - len(candidate_pages))
    workflow = {
        "query": query,
        "sources": source_results,
        "merged": merged_items,
        "source_errors": errors_by_source,
        "documents": documents,
        "images": images,
        "artifact": None,
        "brief": None,
    }
    if include_brief or (save and save_brief):
        workflow["brief"] = render_research_brief(workflow)

    if save:
        artifact_timestamp = utc_timestamp_for_filename()
        if save_brief and workflow.get("brief"):
            brief_save_result = save_research_brief_artifact(
                project_root=project_root,
                workflow=workflow,
                output_dir=selected_output_dir,
                query=query,
                timestamp=artifact_timestamp,
            )
            if not brief_save_result.get("success"):
                return brief_save_result
        save_result = save_research_json_artifact(
            project_root=project_root,
            workflow=workflow,
            output_dir=selected_output_dir,
            query=query,
            timestamp=artifact_timestamp,
        )
        if not save_result.get("success"):
            return save_result

    workflow["handoff"] = build_workflow_handoff(
        workflow=workflow,
        project_root=project_root,
        output_dir=selected_output_dir if save else "",
        entrypoint="mcp",
    )

    return _ok(
        workflow,
        source_count=len(selected_sources),
        candidate_count=len(candidate_pages),
        document_count=len(documents),
        crawl_error_count=crawl_error_count,
        source_error_count=len(errors_by_source),
        image_count=len(images),
        skipped_item_count=skipped_item_count,
        render_js=bool(render_js),
        retries=retries,
        brief_included=bool(workflow.get("brief")),
        saved=bool(workflow.get("artifact")),
        brief_saved=bool((workflow.get("brief") or {}).get("artifact")),
        handoff_schema=workflow["handoff"]["schema"],
    )


def workflow_document_from_crawl(
    query: str,
    page: Dict,
    crawl_result: Dict,
    attempt_count: int,
) -> Dict:
    page_url = page["url"]
    document = {
        "query": query,
        "source": page.get("source"),
        "url": page_url,
        "title": page.get("title"),
        "snippet": page.get("snippet"),
        "score": page.get("score"),
        "success": bool(crawl_result.get("success")),
        "error": crawl_result.get("error"),
        "crawl_attempts": attempt_count,
    }
    if not crawl_result.get("success"):
        return document

    crawl_data = crawl_result.get("data") or {}
    document.update(
        {
            "final_url": crawl_data.get("final_url"),
            "status_code": crawl_data.get("status_code"),
            "content_type": crawl_data.get("content_type"),
            "page_title": crawl_data.get("title") or page.get("title"),
            "description": crawl_data.get("description"),
            "text": crawl_data.get("text") or "",
            "text_truncated": bool(crawl_data.get("text_truncated")),
            "links": (crawl_data.get("links") or [])[:20],
            "images": (crawl_data.get("images") or [])[:30],
        }
    )
    return document


def image_confidence(query: str, page: Dict, image: Dict) -> float:
    terms = [term.lower() for term in re.findall(r"\w+", query) if len(term) > 1]
    alt = str(image.get("alt") or "").lower()
    page_title = str(page.get("title") or "").lower()
    snippet = str(page.get("snippet") or "").lower()

    score = 0.35
    if terms and any(term in alt for term in terms):
        score += 0.3
    if terms and any(term in page_title for term in terms):
        score += 0.2
    if terms and any(term in snippet for term in terms):
        score += 0.1
    if image.get("width") or image.get("height"):
        score += 0.05
    if page.get("score"):
        score += min(0.1, _score_or_default(page.get("score"), 0) / 1000)
    return round(min(score, 1.0), 3)


def _score_or_default(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: int, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_TOOLKIT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
