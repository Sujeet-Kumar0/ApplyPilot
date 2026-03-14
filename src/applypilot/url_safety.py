"""Utilities for safe hostname and path matching."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_hostname(hostname: str | None) -> str:
    """Return a normalized hostname for safe comparisons."""
    return (hostname or "").strip().lower().rstrip(".")


def parse_hostname(url: str | None) -> str:
    """Parse and normalize the hostname from a URL."""
    if not url:
        return ""
    return normalize_hostname(urlparse(url).hostname)


def host_matches(host: str | None, domain: str) -> bool:
    """Return True for an exact domain match or a true subdomain."""
    normalized_host = normalize_hostname(host)
    normalized_domain = normalize_hostname(domain)
    if not normalized_host or not normalized_domain:
        return False
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def host_matches_any(host: str | None, domains: list[str] | tuple[str, ...] | set[str]) -> bool:
    """Return True if the host matches any exact domain or true subdomain."""
    return any(host_matches(host, domain) for domain in domains)


def subdomain_prefix(host: str | None, domain: str) -> str | None:
    """Return the subdomain prefix before a matched suffix."""
    normalized_host = normalize_hostname(host)
    normalized_domain = normalize_hostname(domain)
    if not host_matches(normalized_host, normalized_domain):
        return None
    if normalized_host == normalized_domain:
        return None
    return normalized_host[: -(len(normalized_domain) + 1)]


def path_segments(path: str | None) -> list[str]:
    """Return cleaned path segments."""
    return [segment for segment in (path or "").split("/") if segment]


def is_algolia_queries_url(url: str) -> bool:
    """Return True only for real Algolia query endpoints."""
    parsed = urlparse(url)
    if not host_matches(parsed.hostname, "algolia.net"):
        return False
    segments = path_segments(parsed.path)
    return bool(segments) and segments[-1] == "queries"
