#!/usr/bin/env python3
"""Review saved Research Toolkit artifacts for readability and reuse."""

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_ARTIFACT_GLOB = "output/research/**/*.json"
DEFAULT_REPORT_PATH = "output/research/artifact-reviews/latest-review.md"
MIN_BRIEF_CHARS = 200
MIN_EVIDENCE_TEXT_CHARS = 500
OPENVERSE_SOURCE = "image:openverse"


def find_artifacts(paths: Optional[Iterable[str]], directory: str, latest: int) -> List[str]:
    selected = []
    if paths:
        selected.extend(paths)
    else:
        pattern = os.path.join(directory, "**", "*.json") if directory else DEFAULT_ARTIFACT_GLOB
        selected.extend(glob.glob(pattern, recursive=True))

    artifacts = []
    for path in selected:
        if os.path.isdir(path):
            artifacts.extend(glob.glob(os.path.join(path, "**", "*.json"), recursive=True))
        else:
            artifacts.append(path)

    unique_paths = sorted(
        {os.path.abspath(path) for path in artifacts},
        key=lambda path: os.path.getmtime(path) if os.path.exists(path) else 0,
        reverse=True,
    )
    if latest > 0:
        return unique_paths[:latest]
    return unique_paths


def review_artifact(path: str, project_root: str) -> Dict[str, Any]:
    payload, error = _load_json_file(path)
    if not isinstance(payload, dict):
        return {
            "path": _relative_path(path, project_root),
            "success": False,
            "quality_status": "unreadable",
            "score": 0,
            "warnings": ["json_unreadable"],
            "license_warnings": [],
            "error": error,
            "query": None,
            "counts": {},
            "sources": [],
            "key_documents": [],
        }

    documents = payload.get("documents") or []
    successful_documents = [document for document in documents if document.get("success")]
    failed_documents = [document for document in documents if not document.get("success")]
    source_errors = payload.get("source_errors") or []
    images = payload.get("images") or []
    image_summary = summarize_image_candidates(images)
    brief = payload.get("brief") or {}
    brief_content = brief.get("content") or ""
    total_text_chars = sum(len(document.get("text") or "") for document in successful_documents)
    warnings = artifact_warnings(
        payload=payload,
        successful_documents=successful_documents,
        failed_documents=failed_documents,
        source_errors=source_errors,
        brief_content=brief_content,
        total_text_chars=total_text_chars,
    )
    score = artifact_score(
        successful_documents=successful_documents,
        failed_documents=failed_documents,
        source_errors=source_errors,
        brief_content=brief_content,
        total_text_chars=total_text_chars,
        source_count=len(payload.get("sources") or {}),
    )
    return {
        "path": _relative_path(path, project_root),
        "success": True,
        "quality_status": quality_status(score, warnings),
        "score": score,
        "warnings": warnings,
        "license_warnings": image_summary["license_warnings"],
        "query": payload.get("query"),
        "counts": {
            "sources": len(payload.get("sources") or {}),
            "documents": len(documents),
            "successful_documents": len(successful_documents),
            "failed_documents": len(failed_documents),
            "images": image_summary["images"],
            "openverse_images": image_summary["openverse_images"],
            "page_images": image_summary["page_images"],
            "openverse_license_complete": image_summary["openverse_license_complete"],
            "license_verification_required_images": image_summary["license_verification_required_images"],
            "source_errors": len(source_errors),
            "brief_chars": len(brief_content),
            "evidence_text_chars": total_text_chars,
        },
        "sources": sorted((payload.get("sources") or {}).keys()),
        "artifact": _artifact_paths(payload, project_root),
        "key_documents": key_documents(successful_documents),
        "source_errors": summarize_source_errors(source_errors),
        "page_errors": summarize_page_errors(failed_documents),
    }


def artifact_warnings(
    payload: Dict[str, Any],
    successful_documents: List[Dict[str, Any]],
    failed_documents: List[Dict[str, Any]],
    source_errors: List[Dict[str, Any]],
    brief_content: str,
    total_text_chars: int,
) -> List[str]:
    warnings = []
    if not payload.get("sources"):
        warnings.append("no_sources")
    if not successful_documents:
        warnings.append("no_successful_documents")
    if failed_documents:
        warnings.append("page_errors_present")
    if source_errors:
        warnings.append("source_errors_present")
    if not brief_content:
        warnings.append("missing_brief")
    elif len(brief_content) < MIN_BRIEF_CHARS:
        warnings.append("short_brief")
    if successful_documents and total_text_chars < MIN_EVIDENCE_TEXT_CHARS:
        warnings.append("low_evidence_text")
    return warnings


def artifact_score(
    successful_documents: List[Dict[str, Any]],
    failed_documents: List[Dict[str, Any]],
    source_errors: List[Dict[str, Any]],
    brief_content: str,
    total_text_chars: int,
    source_count: int,
) -> int:
    score = 0
    if successful_documents:
        score += 35
    if not failed_documents:
        score += 15
    if not source_errors:
        score += 15
    if len(brief_content or "") >= MIN_BRIEF_CHARS:
        score += 15
    if total_text_chars >= MIN_EVIDENCE_TEXT_CHARS:
        score += 15
    if source_count > 0:
        score += 5
    return min(score, 100)


def quality_status(score: int, warnings: List[str]) -> str:
    if score >= 80 and not warnings:
        return "ready"
    if score >= 40:
        return "partial"
    return "needs_attention"


def summarize_image_candidates(images: Iterable[Any]) -> Dict[str, Any]:
    selected_images = list(images or [])
    openverse_images = [
        image
        for image in selected_images
        if isinstance(image, dict) and image.get("source") == OPENVERSE_SOURCE
    ]
    complete_openverse_licenses = sum(
        1
        for image in openverse_images
        if all(image.get(field) for field in ("license", "license_url", "attribution"))
    )
    verification_required = sum(
        1
        for image in openverse_images
        if image.get("license_verification_required") is True
    )
    license_warnings = []
    if complete_openverse_licenses < len(openverse_images):
        license_warnings.append("openverse_license_metadata_incomplete")
    if verification_required:
        license_warnings.append("openverse_license_verification_required")
    return {
        "images": len(selected_images),
        "openverse_images": len(openverse_images),
        "page_images": len(selected_images) - len(openverse_images),
        "openverse_license_complete": complete_openverse_licenses,
        "license_verification_required_images": verification_required,
        "license_warnings": license_warnings,
    }


def key_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected = []
    for document in documents[:5]:
        selected.append(
            {
                "title": document.get("page_title") or document.get("title") or document.get("url"),
                "url": document.get("final_url") or document.get("url"),
                "source": document.get("source"),
                "status_code": document.get("status_code"),
                "text_chars": len(document.get("text") or ""),
                "link_count": len(document.get("links") or []),
                "image_count": len(document.get("images") or []),
            }
        )
    return selected


def summarize_source_errors(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "source": error.get("source"),
            "code": error.get("code"),
            "message": _clip(error.get("message"), 160),
        }
        for error in errors[:5]
    ]


def summarize_page_errors(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    page_errors = []
    for document in documents[:5]:
        error = document.get("error") or {}
        page_errors.append(
            {
                "title": document.get("title") or document.get("url"),
                "url": document.get("url"),
                "code": error.get("code"),
                "message": _clip(error.get("message"), 160),
            }
        )
    return page_errors


def review_collection(paths: List[str], project_root: str) -> Dict[str, Any]:
    reviews = [review_artifact(path, project_root) for path in paths]
    status_counts = {}
    for review in reviews:
        status = review.get("quality_status") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "success": bool(reviews),
        "artifact_count": len(reviews),
        "status_counts": status_counts,
        "average_score": round(sum(review.get("score", 0) for review in reviews) / len(reviews), 1) if reviews else 0,
        "openverse_image_count": sum((review.get("counts") or {}).get("openverse_images", 0) for review in reviews),
        "page_image_count": sum((review.get("counts") or {}).get("page_images", 0) for review in reviews),
        "openverse_license_complete_count": sum(
            (review.get("counts") or {}).get("openverse_license_complete", 0) for review in reviews
        ),
        "license_verification_required_count": sum(
            (review.get("counts") or {}).get("license_verification_required_images", 0) for review in reviews
        ),
        "license_warning_count": sum(len(review.get("license_warnings") or []) for review in reviews),
        "reviews": reviews,
    }


def render_markdown_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Research Artifact Review",
        "",
        f"- Artifacts: {report.get('artifact_count', 0)}",
        f"- Average score: {report.get('average_score', 0)}",
        f"- Status counts: {json.dumps(report.get('status_counts') or {}, ensure_ascii=False, sort_keys=True)}",
        f"- License warnings: {report.get('license_warning_count', 0)}",
        "",
    ]
    for review in report.get("reviews") or []:
        lines.extend(
            [
                f"## {review.get('query') or review.get('path') or 'Unreadable artifact'}",
                "",
                f"- Status: `{review.get('quality_status')}`",
                f"- Score: `{review.get('score')}`",
                f"- Artifact: `{review.get('path')}`",
            ]
        )
        warnings = review.get("warnings") or []
        lines.append(f"- Warnings: {', '.join(f'`{warning}`' for warning in warnings) if warnings else 'none'}")
        license_warnings = review.get("license_warnings") or []
        lines.append(f"- License warnings: {', '.join(f'`{warning}`' for warning in license_warnings) if license_warnings else 'none'}")
        counts = review.get("counts") or {}
        if counts:
            lines.append(
                "- Counts: "
                f"{counts.get('successful_documents', 0)}/{counts.get('documents', 0)} documents usable, "
                f"{counts.get('images', 0)} images "
                f"({counts.get('openverse_images', 0)} Openverse, {counts.get('page_images', 0)} page), "
                f"{counts.get('source_errors', 0)} source errors, "
                f"{counts.get('brief_chars', 0)} brief chars"
            )
        documents = review.get("key_documents") or []
        if documents:
            lines.extend(["", "Key documents:"])
            for document in documents:
                title = document.get("title") or document.get("url") or "Untitled"
                url = document.get("url") or ""
                lines.append(
                    f"- {_markdown_link(title, url)} "
                    f"({document.get('text_chars', 0)} chars, "
                    f"{document.get('link_count', 0)} links, "
                    f"{document.get('image_count', 0)} images)"
                )
        if review.get("source_errors"):
            lines.extend(["", "Source errors:"])
            for error in review["source_errors"]:
                lines.append(f"- `{error.get('source')}` `{error.get('code')}` {error.get('message') or ''}".rstrip())
        if review.get("page_errors"):
            lines.extend(["", "Page errors:"])
            for error in review["page_errors"]:
                lines.append(f"- {_markdown_link(error.get('title'), error.get('url'))}: `{error.get('code')}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(content: str, path: str, project_root: str) -> Dict[str, Any]:
    output_path = path or DEFAULT_REPORT_PATH
    output_path = _resolve_project_path(output_path, project_root)
    if not output_path:
        return {"success": False, "error": {"code": "UNSAFE_OUTPUT_PATH", "message": "Report path must stay inside project"}}
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(content)
    except OSError as ex:
        return {"success": False, "error": {"code": "WRITE_ERROR", "message": str(ex)}}
    return {"success": True, "path": _relative_path(output_path, project_root)}


def exit_code_for_report(report: Dict[str, Any]) -> int:
    if not report.get("success"):
        return 2
    unreadable = (report.get("status_counts") or {}).get("unreadable", 0)
    return 3 if unreadable else 0


def run_review(args: argparse.Namespace) -> int:
    project_root = os.getcwd()
    paths = find_artifacts(args.artifact, args.directory, args.latest)
    report = review_collection(paths, project_root)
    report["status"] = "ran" if paths else "no_artifacts"
    if args.format == "markdown":
        output = render_markdown_report(report)
    else:
        output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)

    write_result = None
    if args.write_report:
        write_result = write_report(output, args.write_report, project_root)
        report["report_artifact"] = write_result
        if not write_result.get("success"):
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 3

    if args.format == "markdown":
        print(output)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code_for_report(report)


def _load_json_file(path: Optional[str]) -> tuple:
    if not path:
        return None, {"code": "MISSING_PATH", "message": "Artifact path is missing"}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle), {}
    except (OSError, json.JSONDecodeError) as ex:
        return None, {"code": ex.__class__.__name__, "message": str(ex)}


def _artifact_paths(payload: Dict[str, Any], project_root: str) -> Dict[str, Optional[str]]:
    artifact = payload.get("artifact") or {}
    brief = payload.get("brief") or {}
    brief_artifact = brief.get("artifact") or {}
    return {
        "json": _relative_path(artifact.get("path"), project_root),
        "markdown": _relative_path(brief_artifact.get("path"), project_root),
    }


def _path_inside_project(path: Optional[str], project_root: str) -> bool:
    return _resolve_project_path(path, project_root) is not None


def _relative_path(path: Optional[str], project_root: str) -> Optional[str]:
    abs_path = _resolve_project_path(path, project_root)
    if not abs_path:
        return None
    return os.path.relpath(abs_path, os.path.realpath(os.path.abspath(project_root)))


def _resolve_project_path(path: Optional[str], project_root: str) -> Optional[str]:
    if not path:
        return None
    root = os.path.realpath(os.path.abspath(project_root))
    candidate = path if os.path.isabs(path) else os.path.join(root, path)
    resolved = os.path.realpath(os.path.abspath(candidate))
    try:
        if os.path.commonpath([root, resolved]) != root:
            return None
    except ValueError:
        return None
    return resolved


def _clip(value: Any, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _markdown_link(label: Any, url: Any) -> str:
    clean_label = str(label or url or "untitled").replace("[", "\\[").replace("]", "\\]")
    clean_url = str(url or "").strip()
    if clean_url.startswith("http://") or clean_url.startswith("https://"):
        return f"[{clean_label}]({clean_url})"
    return clean_label


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", action="append", help="Artifact JSON path. May be passed multiple times.")
    parser.add_argument("--directory", default="output/research", help="Directory to scan when --artifact is omitted.")
    parser.add_argument("--latest", type=int, default=10, help="Limit to the latest N artifacts. Use 0 for all.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json", help="Report output format.")
    parser.add_argument("--write-report", help="Optional project-local path to write the rendered report.")
    return parser


def main() -> int:
    return run_review(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
