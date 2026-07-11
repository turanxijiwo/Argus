"""Unified discovery for books, papers, and university course resources."""

import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from .research_resource_normalize import (
    ATOM,
    arxiv_title_query,
    atom_text,
    normalize_arxiv_paper,
    normalize_course,
    normalize_crossref_paper,
    normalize_open_library_book,
    normalize_openreview_paper,
    normalize_semantic_paper,
    parse_gutenberg_book,
    rank_resources,
)
from .research_runtime import create_research_session


GUTENBERG_SEARCH_URL = "https://www.gutenberg.org/ebooks/search.opds/"
GUTENBERG_DETAIL_LIMIT = 5
RESOURCE_TYPES = {"book", "paper", "course"}
ACCESS_FILTERS = {"any", "open", "borrowable"}


class ResearchResourceTools:
    """Find access-aware resources without bypassing access controls."""

    def __init__(
        self,
        project_root: Optional[str] = None,
        external_api: Optional[Any] = None,
        topic_search: Optional[Callable[..., Dict]] = None,
        session: Optional[requests.Session] = None,
    ):
        self.project_root = project_root
        self.external_api = external_api
        self.topic_search = topic_search
        self.session = session or create_research_session()

    def find_research_resource(
        self,
        query: str,
        resource_type: str,
        institution: Optional[str] = None,
        language: Optional[str] = None,
        access: str = "any",
        limit: int = 10,
        timeout: int = 20,
    ) -> Dict:
        query = " ".join(str(query or "").split())
        resource_type = str(resource_type or "").strip().lower()
        access = str(access or "any").strip().lower()
        if not query:
            return _err("query cannot be empty", "INVALID_QUERY")
        if resource_type not in RESOURCE_TYPES:
            return _err(
                f"Unsupported resource_type: {resource_type}",
                "INVALID_RESOURCE_TYPE",
                supported=sorted(RESOURCE_TYPES),
            )
        if access not in ACCESS_FILTERS:
            return _err(
                f"Unsupported access filter: {access}",
                "INVALID_ACCESS_FILTER",
                supported=sorted(ACCESS_FILTERS),
            )

        limit = _safe_int(limit, 10, 1, 25)
        timeout = _safe_int(timeout, 20, 5, 60)
        if resource_type == "book":
            resources, errors, sources = self._search_books(query, limit, timeout)
        elif resource_type == "paper":
            resources, errors, sources = self._search_papers(query, limit)
        else:
            resources, errors, sources = self._search_courses(
                query, institution, language, limit
            )

        resources = rank_resources(resources, query, access, language, limit)
        return _ok(
            {
                "query": query,
                "resource_type": resource_type,
                "access_filter": access,
                "resources": resources,
                "source_errors": errors,
                "policy": {
                    "source_scope": "official, open, borrow, preview, or metadata sources",
                    "bypass_access_controls": False,
                },
            },
            query=query,
            resource_type=resource_type,
            count=len(resources),
            open_count=sum(item["access"].startswith("open_") for item in resources),
            source_error_count=len(errors),
            sources_attempted=sources,
        )

    def _search_books(
        self, query: str, limit: int, timeout: int
    ) -> Tuple[List[Dict], List[Dict], List[str]]:
        resources: List[Dict] = []
        errors: List[Dict] = []
        sources = ["open_library", "project_gutenberg"]
        if not self.external_api:
            errors.append(
                _source_error(
                    "open_library",
                    "ADAPTER_UNAVAILABLE",
                    "External API adapter is unavailable",
                )
            )
        else:
            try:
                response = self.external_api.search_books(query=query, limit=limit)
                if response.get("success"):
                    books = (response.get("data") or {}).get("books", [])
                    resources.extend(normalize_open_library_book(book) for book in books)
                else:
                    errors.append(_result_error("open_library", response))
            except Exception as ex:
                errors.append(_source_error("open_library", "SOURCE_ERROR", str(ex)))

        gutenberg_resources, gutenberg_error = self._search_gutenberg(
            query, limit, timeout
        )
        resources.extend(gutenberg_resources)
        if gutenberg_error:
            errors.append(gutenberg_error)
        return resources, errors, sources

    def _search_gutenberg(
        self, query: str, limit: int, timeout: int
    ) -> Tuple[List[Dict], Optional[Dict]]:
        try:
            response = self.session.get(
                GUTENBERG_SEARCH_URL,
                params={"query": query},
                timeout=timeout,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            resources = []
            for entry in root.findall(f"{ATOM}entry")[: min(limit, GUTENBERG_DETAIL_LIMIT)]:
                detail_link = next(
                    (
                        link.get("href")
                        for link in entry.findall(f"{ATOM}link")
                        if link.get("rel") == "subsection"
                    ),
                    None,
                )
                if not detail_link:
                    continue
                detail_url = urljoin(GUTENBERG_SEARCH_URL, detail_link)
                detail_response = self.session.get(detail_url, timeout=timeout)
                detail_response.raise_for_status()
                parsed = parse_gutenberg_book(
                    ET.fromstring(detail_response.content),
                    detail_url,
                    atom_text(entry, "title"),
                )
                if parsed:
                    resources.append(parsed)
            return resources, None
        except (requests.RequestException, ET.ParseError) as ex:
            return [], _source_error("project_gutenberg", "SOURCE_ERROR", str(ex))

    def _search_papers(
        self, query: str, limit: int
    ) -> Tuple[List[Dict], List[Dict], List[str]]:
        sources = ["arxiv", "semantic_scholar", "openreview", "crossref"]
        if not self.external_api:
            errors = [
                _source_error(
                    source,
                    "ADAPTER_UNAVAILABLE",
                    "External API adapter is unavailable",
                )
                for source in sources
            ]
            return [], errors, sources

        specs = [
            (
                "arxiv",
                "papers",
                lambda: self.external_api.search_arxiv(
                    arxiv_title_query(query),
                    max_results=limit,
                    sort_by="relevance",
                ),
                normalize_arxiv_paper,
            ),
            (
                "semantic_scholar",
                "papers",
                lambda: self.external_api.search_semantic_scholar(query, limit=limit),
                normalize_semantic_paper,
            ),
            (
                "openreview",
                "papers",
                lambda: self.external_api.search_openreview(query, limit=limit),
                normalize_openreview_paper,
            ),
            (
                "crossref",
                "works",
                lambda: self.external_api.search_crossref(query, rows=limit),
                normalize_crossref_paper,
            ),
        ]
        resources: List[Dict] = []
        errors: List[Dict] = []
        for source, data_key, call, normalizer in specs:
            try:
                response = call()
                if not response.get("success"):
                    errors.append(_result_error(source, response))
                    continue
                items = (response.get("data") or {}).get(data_key, [])
                resources.extend(normalizer(item) for item in items)
            except Exception as ex:
                errors.append(_source_error(source, "SOURCE_ERROR", str(ex)))
        return resources, errors, sources

    def _search_courses(
        self,
        query: str,
        institution: Optional[str],
        language: Optional[str],
        limit: int,
    ) -> Tuple[List[Dict], List[Dict], List[str]]:
        if not self.topic_search:
            error = _source_error(
                "codex", "ADAPTER_UNAVAILABLE", "Topic search adapter is unavailable"
            )
            return [], [error], ["codex"]
        terms = [
            institution,
            query,
            "official course curriculum syllabus lecture notes assignments",
            language,
        ]
        response = self.topic_search(
            query=" ".join(term for term in terms if term),
            sources=["codex"],
            limit=limit,
        )
        if not response.get("success"):
            return [], [_result_error("codex", response)], ["codex"]
        data = response.get("data") or {}
        resources = [
            normalize_course(item, institution)
            for item in data.get("merged", [])
            if item.get("url")
        ]
        source_errors = [
            _result_error(name, result)
            for name, result in (data.get("sources") or {}).items()
            if not result.get("success")
        ]
        return resources, source_errors, ["codex"]


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _result_error(source: str, response: Dict) -> Dict:
    error = response.get("error") or {}
    return _source_error(
        source,
        error.get("code") or "SOURCE_ERROR",
        error.get("message") or "Source failed",
    )


def _source_error(source: str, code: str, message: str) -> Dict:
    return {"source": source, "code": code, "message": message}


def _ok(data: Any, **summary: Any) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str, **extra: Any) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
