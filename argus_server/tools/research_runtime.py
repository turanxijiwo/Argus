"""Runtime defaults for the Argus research toolkit."""

import importlib.util
from typing import Any, List

import requests

from .research_health import web_search_provider_status


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) ArgusResearch/1.0 Safari/537.36"
)

MAX_HTML_BYTES = 3 * 1024 * 1024
MAX_TEXT_CHARS = 20000
RETRIABLE_CRAWL_ERRORS = {"NETWORK_ERROR", "TIMEOUT", "CRAWL4AI_ERROR"}


def create_research_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def default_workflow_sources(ai_search: Any = None, codex_runner: Any = None) -> List[str]:
    configured_web_sources = [
        f"web:{name}" for name, provider in web_search_provider_status().items()
        if provider["configured"]
    ]
    if ai_search and configured_web_sources:
        return [configured_web_sources[0]]
    if codex_runner or importlib.util.find_spec("openai_codex"):
        return ["codex"]
    return ["local_news", "hackernews", "wikipedia"]
