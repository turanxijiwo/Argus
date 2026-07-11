"""Deterministic citation metadata and BibTeX rendering for research resources."""

import re
from typing import Any, Dict, List, Optional


def build_citation_metadata(
    resource: Dict,
    title: str,
    authors: List[str],
    url: Optional[str],
    resource_type: Optional[str],
    source_id: str,
) -> Dict:
    identifiers = resource.get("identifiers") or {}
    doi = _normalize_doi(_first_value(identifiers.get("doi")))
    arxiv_id = _normalize_arxiv(_first_value(identifiers.get("arxiv")))
    isbn = _first_value(identifiers.get("isbn"))
    year = _year(resource.get("year"))
    institution = _clean_text(resource.get("institution")) or None
    entry_type = "book" if resource_type == "book" else "article" if doi else "misc"
    bibtex_key = _bibtex_key(authors, institution, year, title, source_id)
    fields = {
        "title": title,
        "author": " and ".join(authors) if authors else None,
        "year": year,
        "doi": doi,
        "isbn": isbn,
        "eprint": arxiv_id,
        "archivePrefix": "arXiv" if arxiv_id else None,
        "organization": institution,
        "url": url,
    }
    bibtex = _render_bibtex(entry_type, bibtex_key, fields)
    return {
        key: value
        for key, value in {
            "entry_type": entry_type,
            "bibtex_key": bibtex_key,
            "title": title,
            "authors": authors,
            "year": year,
            "institution": institution,
            "doi": doi,
            "doi_url": f"https://doi.org/{doi}" if doi else None,
            "arxiv_id": arxiv_id,
            "isbn": isbn,
            "url": url,
            "bibtex": bibtex,
        }.items()
        if value not in (None, "", [])
    }


def _render_bibtex(entry_type: str, key: str, fields: Dict[str, Any]) -> str:
    lines = [f"@{entry_type}{{{key},"]
    selected = [(name, value) for name, value in fields.items() if value not in (None, "")]
    for index, (name, value) in enumerate(selected):
        comma = "," if index < len(selected) - 1 else ""
        lines.append(f"  {name} = {{{_escape_bibtex(value)}}}{comma}")
    lines.append("}")
    return "\n".join(lines)


def _bibtex_key(
    authors: List[str],
    institution: Optional[str],
    year: Optional[int],
    title: str,
    source_id: str,
) -> str:
    owner = authors[0].split(",", 1)[0] if authors and "," in authors[0] else (
        authors[0].split()[-1] if authors else institution or source_id
    )
    title_token = next((token for token in re.findall(r"[A-Za-z0-9]+", title) if token), "resource")
    raw_key = f"{owner}{year or 'nd'}{title_token}"
    ascii_key = raw_key.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9_-]+", "", ascii_key).lower() or source_id.lower()


def _escape_bibtex(value: Any) -> str:
    replacements = {
        "\\": "\\textbackslash{}",
        "{": "\\{",
        "}": "\\}",
        "&": "\\&",
        "%": "\\%",
        "#": "\\#",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def _first_value(value: Any) -> Optional[str]:
    if isinstance(value, list):
        value = next((item for item in value if item), None)
    cleaned = _clean_text(value)
    return cleaned or None


def _normalize_doi(value: Optional[str]) -> Optional[str]:
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value or "", flags=re.IGNORECASE) or None


def _normalize_arxiv(value: Optional[str]) -> Optional[str]:
    cleaned = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", value or "", flags=re.IGNORECASE)
    return cleaned.removesuffix(".pdf") or None


def _year(value: Any) -> Optional[int]:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
