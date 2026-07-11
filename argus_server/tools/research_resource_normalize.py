"""Normalization helpers for unified research resource discovery."""

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


ATOM = "{http://www.w3.org/2005/Atom}"
DCTERMS = "{http://purl.org/dc/terms/}"
OPDS_ACQUISITION_REL = "http://opds-spec.org/acquisition"
ACCESS_RANK = {
    "open_download": 5, "open_read": 4, "borrow": 3,
    "preview": 2, "metadata_only": 1, "unverified": 0,
}
OPEN_COURSE_HOSTS = {"ocw.mit.edu", "oyc.yale.edu", "higher.smartedu.cn"}
OFFICIAL_EDU_SUFFIXES = (".edu", ".edu.cn", ".ac.uk", ".edu.au")
FILE_FORMATS = {
    ".pdf": "pdf", ".epub": "epub", ".zip": "zip", ".ppt": "ppt",
    ".pptx": "pptx", ".doc": "doc", ".docx": "docx",
}


def normalize_open_library_book(book: Dict) -> Dict:
    availability = book.get("availability") or {}
    ebook_access = str(book.get("ebook_access") or "no_ebook").lower()
    status = str(availability.get("status") or "").lower()
    if ebook_access == "public" or status in {"open", "full access"}:
        access = "open_read"
    elif ebook_access == "borrowable" or availability.get("is_lendable") or availability.get("available_to_borrow"):
        access = "borrow"
    elif availability.get("is_previewable"):
        access = "preview"
    else:
        access = "metadata_only"
    return _resource(
        "book", book.get("title") or "Untitled book", book.get("authors") or [],
        "open_library", book.get("url"), access,
        year=book.get("first_publish_year"), languages=book.get("languages"),
        identifiers={"isbn": book.get("isbn") or []},
        metadata={"subjects": book.get("subjects") or [], "availability": availability},
    )


def parse_gutenberg_book(root: ET.Element, detail_url: str, fallback_title: str) -> Optional[Dict]:
    entries = root.findall(f"{ATOM}entry")
    if not entries:
        return None
    title = atom_text(entries[0], "title") or fallback_title or "Untitled book"
    creators: List[str] = []
    languages: List[str] = []
    files: List[Dict] = []
    rights = None
    published = None
    for entry in entries:
        creators.extend(atom_text(author, "name") for author in entry.findall(f"{ATOM}author"))
        language = entry.findtext(f"{DCTERMS}language")
        if language:
            languages.append(language)
        rights = rights or entry.findtext(f"{ATOM}rights")
        published = published or entry.findtext(f"{ATOM}published")
        for link in entry.findall(f"{ATOM}link"):
            if link.get("rel") != OPDS_ACQUISITION_REL or not link.get("href"):
                continue
            files.append({
                "url": link.get("href"),
                "format": _format_for_mime(link.get("type")),
                "access": "open_download",
                "title": link.get("title"),
                "mime_type": link.get("type"),
            })
    ebook_id = _first_match(r"/ebooks/(\d+)\.opds", detail_url)
    return _resource(
        "book", title, _unique(creators), "project_gutenberg",
        f"https://www.gutenberg.org/ebooks/{ebook_id}" if ebook_id else detail_url,
        "open_download" if files else "open_read",
        year=_year(published), languages=_unique(languages),
        identifiers={"gutenberg": ebook_id}, file_urls=_unique_files(files),
        license=rights, metadata={"opds_url": detail_url},
    )


def normalize_arxiv_paper(item: Dict) -> Dict:
    pdf = item.get("pdf_url")
    return _resource(
        "paper", item.get("title") or "Untitled paper", item.get("authors") or [], "arxiv",
        item.get("abs_url") or item.get("id"), "open_download" if pdf else "metadata_only",
        year=_year(item.get("published")),
        identifiers={
            "arxiv": _first_match(r"(?:abs/|/)([^/]+)$", item.get("id") or "")
        },
        file_urls=_pdf_file(pdf), metadata={"summary": item.get("summary")},
    )


def normalize_semantic_paper(item: Dict) -> Dict:
    pdf = item.get("pdf_url")
    return _resource(
        "paper", item.get("title") or "Untitled paper", item.get("authors") or [], "semantic_scholar",
        item.get("url"), "open_download" if pdf else "metadata_only",
        year=item.get("year"), identifiers={"semantic_scholar": item.get("id")},
        file_urls=_pdf_file(pdf), metadata={"abstract": item.get("abstract"), "citations": item.get("citations")},
    )


def normalize_openreview_paper(item: Dict) -> Dict:
    pdf = item.get("pdf")
    return _resource(
        "paper", item.get("title") or "Untitled paper", item.get("authors") or [], "openreview",
        item.get("forum_url"), "open_download" if pdf else "metadata_only",
        identifiers={"openreview": item.get("id")}, file_urls=_pdf_file(pdf),
        metadata={"venue": item.get("venue"), "abstract": item.get("abstract")},
    )


def normalize_crossref_paper(item: Dict) -> Dict:
    published = item.get("published") or []
    year = published[0][0] if published and published[0] else None
    return _resource(
        "paper", item.get("title") or "Untitled paper", item.get("authors") or [], "crossref",
        item.get("url"), "metadata_only", year=year, identifiers={"doi": item.get("doi")},
        metadata={"publisher": item.get("publisher"), "venue": item.get("container_title")},
    )


def normalize_course(item: Dict, institution: Optional[str]) -> Dict:
    url = item.get("url")
    host = (urlparse(url).hostname or "").lower()
    open_course_host = host in OPEN_COURSE_HOSTS
    official = open_course_host or host.endswith(OFFICIAL_EDU_SUFFIXES)
    file_format = next(
        (
            fmt
            for suffix, fmt in FILE_FORMATS.items()
            if urlparse(url).path.lower().endswith(suffix)
        ),
        None,
    )
    access = "open_download" if file_format else ("open_read" if open_course_host else "unverified")
    files = [{"url": url, "format": file_format, "access": "open_download"}] if file_format else []
    return _resource(
        "course", item.get("title") or "Untitled course", [], item.get("source") or "codex",
        url, access, institution=institution, file_urls=files,
        verified_open_access=open_course_host,
        metadata={"snippet": item.get("snippet"), "score": item.get("score"), "official_domain": official},
    )


def merge_resources(resources: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for item in resources:
        key = re.sub(r"\W+", "", (item.get("title") or "").casefold()) or item.get("landing_page_url")
        if key not in merged:
            merged[key] = item
            continue
        current = merged[key]
        current["creators"] = _unique(current["creators"] + item["creators"])
        current["languages"] = _unique(current["languages"] + item["languages"])
        current["sources"] = _unique(current["sources"] + item["sources"])
        current["file_urls"] = _unique_files(current["file_urls"] + item["file_urls"])
        current["identifiers"].update({key: value for key, value in item["identifiers"].items() if value})
        current["metadata"]["records"].update(item["metadata"]["records"])
        if ACCESS_RANK[item["access"]] > ACCESS_RANK[current["access"]]:
            current["access"] = item["access"]
            current["landing_page_url"] = item["landing_page_url"] or current["landing_page_url"]
        current["verified_open_access"] = current["verified_open_access"] or item["verified_open_access"]
        current["license"] = current.get("license") or item.get("license")
    return list(merged.values())


def rank_resources(
    resources: List[Dict],
    query: str,
    access: str,
    language: Optional[str],
    limit: int,
) -> List[Dict]:
    ranked = []
    for item in merge_resources(resources):
        if not matches_access(item["access"], access):
            continue
        if not matches_language(item.get("languages") or [], language):
            continue
        item["relevance_score"] = title_relevance(item.get("title") or "", query)
        ranked.append(item)
    ranked.sort(
        key=lambda item: (
            item["relevance_score"],
            ACCESS_RANK.get(item["access"], -1),
        ),
        reverse=True,
    )
    return ranked[:limit]


def title_relevance(title: str, query: str) -> float:
    normalized_title = _normalized_text(title)
    normalized_query = _normalized_text(query)
    if not normalized_title or not normalized_query:
        return 0.0
    if normalized_title == normalized_query:
        return 1.0
    if normalized_query in normalized_title:
        return 0.9
    query_words = set(normalized_query.split())
    title_words = set(normalized_title.split())
    overlap = len(query_words & title_words)
    if not overlap:
        return 0.0
    coverage = overlap / len(query_words)
    precision = overlap / len(title_words)
    return round(coverage * 0.7 + precision * 0.3, 4)


def arxiv_title_query(query: str) -> str:
    escaped = " ".join(str(query or "").replace('"', " ").split())
    return f'ti:"{escaped}"'


def matches_access(value: str, requested: str) -> bool:
    if requested == "any":
        return True
    if requested == "open":
        return value in {"open_download", "open_read"}
    return value in {"open_download", "open_read", "borrow"}


def matches_language(languages: List[str], requested: Optional[str]) -> bool:
    if not requested or not languages:
        return True
    aliases = {
        "en": {"en", "eng", "english"},
        "zh": {"zh", "zho", "chi", "chinese", "中文"},
    }
    target = str(requested).strip().casefold()
    accepted = aliases.get(target, {target})
    return any(str(language).strip().casefold() in accepted for language in languages)


def atom_text(element: ET.Element, name: str) -> str:
    return (element.findtext(f"{ATOM}{name}") or "").strip()


def _resource(
    resource_type: str,
    title: str,
    creators: List[str],
    source: str,
    landing_page_url: Optional[str],
    access: str,
    **extra: Any,
) -> Dict:
    return {
        "resource_type": resource_type,
        "title": title,
        "creators": creators,
        "year": extra.get("year"),
        "institution": extra.get("institution"),
        "languages": extra.get("languages") or [],
        "identifiers": extra.get("identifiers") or {},
        "sources": [source],
        "landing_page_url": landing_page_url,
        "file_urls": extra.get("file_urls") or [],
        "access": access,
        "license": extra.get("license"),
        "verified_open_access": extra.get(
            "verified_open_access", access in {"open_download", "open_read"}
        ),
        "metadata": {"records": {source: extra.get("metadata") or {}}},
    }


def _pdf_file(url: Optional[str]) -> List[Dict]:
    return [{"url": url, "format": "pdf", "access": "open_download"}] if url else []


def _format_for_mime(mime_type: Optional[str]) -> str:
    return {
        "application/epub+zip": "epub",
        "application/x-mobipocket-ebook": "kindle",
        "application/pdf": "pdf",
        "text/plain": "txt",
        "text/html": "html",
    }.get(mime_type or "", "file")


def _year(value: Any) -> Optional[int]:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _first_match(pattern: str, value: str) -> Optional[str]:
    match = re.search(pattern, value or "")
    return match.group(1) if match else None


def _normalized_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _unique(values: List[Any]) -> List[Any]:
    return list(dict.fromkeys(value for value in values if value))


def _unique_files(files: List[Dict]) -> List[Dict]:
    return list({item.get("url"): item for item in files if item.get("url")}.values())
