"""Public-network validation and HTTP transport for Argus research crawling."""

import ipaddress
import os
import socket
from typing import Any, Dict
from urllib.parse import urljoin, urlparse

import requests


_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5
_CODEX_VIRTUAL_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_public_http_url(url: str) -> Dict:
    """Resolve an HTTP URL and reject every non-public destination address."""
    if not is_http_url(url):
        return _err(f"Invalid URL: {url}", code="INVALID_URL", url=url)

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return _err(f"Invalid URL: {url}", code="INVALID_URL", url=url)

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return _err(f"Invalid URL port: {url}", code="INVALID_URL", url=url)

    try:
        literal_address = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        literal_address = None

    if literal_address is not None:
        addresses = [str(literal_address)]
    else:
        try:
            address_info = socket.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except (OSError, UnicodeError) as ex:
            return _err(
                f"Could not resolve URL host: {hostname}",
                code="DNS_RESOLUTION_ERROR",
                url=url,
                detail=str(ex),
            )
        addresses = sorted({item[4][0].split("%", 1)[0] for item in address_info if item[4]})
    if not addresses:
        return _err(
            f"Could not resolve URL host: {hostname}",
            code="DNS_RESOLUTION_ERROR",
            url=url,
        )

    non_public_addresses = []
    for address in addresses:
        try:
            resolved_address = ipaddress.ip_address(address)
            is_codex_virtual_address = (
                literal_address is None
                and bool(os.environ.get("CODEX_SANDBOX"))
                and resolved_address in _CODEX_VIRTUAL_NETWORK
            )
            if not resolved_address.is_global and not is_codex_virtual_address:
                non_public_addresses.append(address)
        except ValueError:
            return _err(
                f"Host resolved to an invalid address: {hostname}",
                code="DNS_RESOLUTION_ERROR",
                url=url,
            )

    if non_public_addresses:
        return _err(
            "URL resolves to a non-public network address",
            code="UNSAFE_URL",
            url=url,
            hostname=hostname,
            addresses=non_public_addresses,
        )

    return _ok({"url": url, "hostname": hostname, "addresses": addresses})


def fetch_html(session: requests.Session, url: str, timeout: int, max_html_bytes: int) -> Dict:
    try:
        current_url = url
        visited_urls = set()
        for redirect_count in range(_MAX_REDIRECTS + 1):
            validation = validate_public_http_url(current_url)
            if not validation.get("success"):
                return validation
            if current_url in visited_urls:
                return _err(
                    "Redirect loop detected",
                    code="REDIRECT_LOOP",
                    url=current_url,
                )
            visited_urls.add(current_url)

            response = session.get(
                current_url,
                timeout=timeout,
                stream=True,
                allow_redirects=False,
            )
            if response.status_code in _REDIRECT_STATUS_CODES:
                location = response.headers.get("location")
                response.close()
                if not location:
                    return _err(
                        "Redirect response is missing a Location header",
                        code="INVALID_REDIRECT",
                        url=current_url,
                    )
                if redirect_count >= _MAX_REDIRECTS:
                    return _err(
                        "Too many redirects",
                        code="TOO_MANY_REDIRECTS",
                        url=current_url,
                        max_redirects=_MAX_REDIRECTS,
                    )
                current_url = urljoin(response.url or current_url, location)
                continue

            try:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    content.extend(chunk)
                    if len(content) > max_html_bytes:
                        return _err(
                            "HTML response is too large",
                            code="RESPONSE_TOO_LARGE",
                            max_bytes=max_html_bytes,
                        )
                encoding = response.encoding or response.apparent_encoding or "utf-8"
                html = bytes(content).decode(encoding, errors="replace")
                return _ok(
                    {
                        "html": html,
                        "final_url": response.url or current_url,
                        "status_code": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                    },
                    bytes=len(content),
                )
            finally:
                response.close()
    except requests.Timeout:
        return _err("Request timed out", code="TIMEOUT", url=url)
    except requests.RequestException as ex:
        return _err(f"Request failed: {ex}", code="NETWORK_ERROR", url=url)


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "RESEARCH_NETWORK_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}
