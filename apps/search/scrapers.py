"""Fetch a URL and extract clean main-article text.

Three-step cascade for hostile sites:
    1. ``normalize_url``     — rewrite known patterns (e.g. reddit.com → old.reddit.com)
    2. Direct fetch           — httpx with browser-like headers, trafilatura/bs4 cascade
    3. Jina Reader fallback   — public free hosted service that returns clean markdown
                                of any URL; handles JS-rendered SPAs, mild bot detection,
                                and most non-paywalled content. No API key needed for
                                the anonymous tier; supply ``JINA_API_KEY`` for higher
                                rate limits.

Both libraries (trafilatura, bs4) are imported lazily so unrelated requests
don't pay their cost.

SSRF: we reject the obvious internal hosts (Docker service names, loopback,
private IPv4/IPv6). For real production you'd want an outbound proxy with an
explicit allowlist — Phase 4.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# Browser-like UA helps slip past simple UA filters; doesn't fool Cloudflare
# but improves baseline success on small sites.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
}

HTTP_TIMEOUT = 15.0
MAX_HTML_BYTES = 5 * 1024 * 1024  # 5 MB cap per page

# Jina Reader (https://jina.ai/reader) — hosted, returns clean markdown
JINA_READER_PREFIX = "https://r.jina.ai/"
JINA_TIMEOUT = 30.0
JINA_MIN_TEXT_LENGTH = 100

# URL transforms for sites with bot-friendly variants of the same content.
URL_TRANSFORMS: list[tuple[re.Pattern[str], str]] = [
    # Reddit's modern UI is JS-only — old.reddit serves the post + comments
    # straight from the server and is much easier to extract.
    (re.compile(r"^https?://(?:www\.)?reddit\.com/", re.IGNORECASE), "https://old.reddit.com/"),
]

# Block our own service names (and any other obvious internals) at the source.
DENY_HOSTNAMES = {
    "localhost", "0.0.0.0",
    "db", "redis", "web", "celery", "realtime", "searxng", "ollama",
    "neuroseek_db", "neuroseek_redis", "neuroseek_web",
    "neuroseek_celery", "neuroseek_realtime", "neuroseek_searxng",
    "neuroseek_ollama",
}


class FetchError(RuntimeError):
    def __init__(self, message: str, *, friendly: str | None = None):
        super().__init__(message)
        self.friendly = friendly or message


class ScrapeError(RuntimeError):
    def __init__(self, message: str, *, friendly: str | None = None):
        super().__init__(message)
        self.friendly = friendly or message


class UnsafeURLError(ValueError):
    pass


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------
def normalize_url(url: str) -> str:
    """Rewrite known URL patterns to bot-friendlier variants."""
    for pattern, replacement in URL_TRANSFORMS:
        new_url, n = pattern.subn(replacement, url, count=1)
        if n:
            logger.info("URL rewrite: %s → %s", url, new_url)
            return new_url
    return url


def assert_url_safe(url: str) -> None:
    """Raise UnsafeURLError if the URL targets an obvious private resource."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"unsupported scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeURLError("missing hostname")
    if host in DENY_HOSTNAMES or host.endswith((".local", ".internal", ".lan")):
        raise UnsafeURLError(f"hostname {host!r} is not allowed")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeURLError(f"IP {host} is not allowed")
    except ValueError:
        # not a literal IP, ok
        pass


# ---------------------------------------------------------------------------
# Direct fetch + extractors
# ---------------------------------------------------------------------------
def fetch_html(url: str) -> tuple[str, dict[str, Any]]:
    """GET ``url`` and return (text_body, metadata). Raises FetchError on failure."""
    assert_url_safe(url)
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise FetchError(f"timeout: {e}", friendly="The page took too long to respond. The site may be slow or blocking automated requests.") from e
    except httpx.ConnectError as e:
        raise FetchError(f"connect: {e}", friendly="Could not connect to the site. Check the URL.") from e
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        friendly = {
            401: "The page requires login (401). NeuroSeek can't fetch authenticated content.",
            403: "The site refused our request (403). Some sites block automated crawlers.",
            404: "The page does not exist (404).",
            429: "The site rate-limited us (429). Try again in a minute.",
            500: "The site returned a server error (500).",
            502: "The site is offline (502 bad gateway).",
            503: "The site is unavailable (503).",
        }.get(code, f"The site returned an error ({code}).")
        raise FetchError(f"HTTP {code}", friendly=friendly) from e
    except httpx.HTTPError as e:
        raise FetchError(f"fetch failed: {e}", friendly=f"Could not fetch the URL: {e}") from e

    ctype = resp.headers.get("content-type", "")
    if not (ctype.startswith("text/html") or ctype.startswith("application/xhtml")):
        raise FetchError(
            f"not an HTML response (content-type: {ctype or 'unknown'})",
            friendly=f"That URL returned {ctype or 'an unknown content type'} instead of HTML. We only ingest web pages.",
        )
    if len(resp.content) > MAX_HTML_BYTES:
        mb = MAX_HTML_BYTES // (1024 * 1024)
        raise FetchError(
            f"response too large ({len(resp.content)} bytes)",
            friendly=f"The page is larger than {mb} MB. Try a smaller article.",
        )

    return resp.text, {
        "final_url": str(resp.url),
        "status_code": resp.status_code,
        "content_type": ctype,
        "size_bytes": len(resp.content),
    }


def extract_main_text(html: str, url: str = "") -> tuple[str, dict[str, Any]]:
    """Cascade through extractors until one yields >200 chars of text."""
    # 1. trafilatura — primary
    try:
        import trafilatura

        meta = {}
        title = ""
        try:
            md = trafilatura.extract_metadata(html)
            if md:
                title = (md.title or "").strip()
                meta = {"author": md.author, "date": md.date, "sitename": md.sitename}
        except Exception:
            pass

        text = trafilatura.extract(
            html,
            url=url or None,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
        )
        if text and len(text) > 200:
            out_meta = {"extractor": "trafilatura", "title": title}
            out_meta.update({k: v for k, v in meta.items() if v})
            return text.strip(), out_meta
    except Exception as e:
        logger.warning("trafilatura extraction failed: %s", e)

    # 2. BeautifulSoup last-resort
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "form"]):
            tag.decompose()
        title_el = soup.find("title")
        title = title_el.get_text(strip=True) if title_el else ""
        body = soup.find("body") or soup
        text = "\n".join(line.strip() for line in body.get_text("\n").splitlines() if line.strip())
        if text and len(text) > 50:
            return text, {"extractor": "bs4", "title": title}
    except Exception as e:
        logger.warning("bs4 extraction failed: %s", e)

    raise ScrapeError(
        "no extractor produced usable text",
        friendly=(
            "We fetched the page but couldn't extract any meaningful text from it. "
            "It may be JavaScript-rendered, an image-only page, or paywalled."
        ),
    )


# ---------------------------------------------------------------------------
# Jina Reader fallback
# ---------------------------------------------------------------------------
def fetch_via_jina(url: str) -> tuple[str, dict[str, Any]]:
    """Fetch the URL through Jina Reader and return clean markdown.

    Jina Reader (r.jina.ai) handles bot detection and JS rendering. The free
    anonymous tier needs no API key but is rate-limited; supply
    ``JINA_API_KEY`` (free signup at jina.ai) for higher quotas.
    """
    target = JINA_READER_PREFIX + url
    headers = {
        "User-Agent": "NeuroSeekBot/0.2 (+research-assistant)",
        "Accept": "text/markdown, text/plain;q=0.9, */*;q=0.5",
    }
    api_key = (getattr(settings, "JINA_API_KEY", "") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=JINA_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(target, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        raise FetchError(
            f"Jina Reader HTTP {code}",
            friendly=f"Jina Reader fallback returned {code} for this URL.",
        ) from e
    except httpx.HTTPError as e:
        raise FetchError(
            f"Jina Reader request failed: {e}",
            friendly="Jina Reader fallback could not be reached.",
        ) from e

    text = (resp.text or "").strip()
    if len(text) < JINA_MIN_TEXT_LENGTH:
        raise ScrapeError(
            f"Jina Reader returned too little text ({len(text)} chars)",
            friendly="Jina Reader could not extract meaningful content from this page.",
        )
    return text, {
        "extractor": "jina_reader",
        "final_url": url,
        "size_bytes": len(text),
    }


# ---------------------------------------------------------------------------
# Public entry point — cascade
# ---------------------------------------------------------------------------
def scrape_url(url: str) -> tuple[str, dict[str, Any]]:
    """Fetch + extract main content with a 3-step cascade.

    Step 1: rewrite URL if a known transform applies (e.g. reddit → old.reddit).
    Step 2: direct fetch with browser-like headers, then trafilatura/bs4.
    Step 3: Jina Reader fallback (if enabled) for sites that fail step 2.

    Returns ``(text, metadata)``. Metadata's ``extractor`` field tells you
    which step succeeded: ``trafilatura`` / ``bs4`` / ``jina_reader``.
    """
    url = normalize_url(url)
    assert_url_safe(url)

    primary_error: Exception | None = None

    # Step 2 — direct fetch + extractors
    try:
        html, fetch_meta = fetch_html(url)
        text, extract_meta = extract_main_text(html, url=fetch_meta.get("final_url", url))
        return text, {**fetch_meta, **extract_meta}
    except (FetchError, ScrapeError) as e:
        primary_error = e
        logger.info("primary scrape failed for %s (%s) — trying Jina Reader", url, e)

    # Step 3 — Jina Reader fallback
    use_jina = bool(getattr(settings, "USE_JINA_FALLBACK", True))
    if use_jina:
        try:
            text, jina_meta = fetch_via_jina(url)
            jina_meta["primary_error"] = str(primary_error) if primary_error else ""
            return text, jina_meta
        except (FetchError, ScrapeError) as e:
            logger.warning("Jina Reader fallback failed for %s: %s", url, e)

    # All methods failed
    base_msg = getattr(primary_error, "friendly", str(primary_error)) if primary_error else "unknown failure"
    raise ScrapeError(
        "all extractors failed",
        friendly=(
            f"{base_msg} (also tried the Jina Reader fallback). "
            "Try a different source or disable USE_JINA_FALLBACK if it's misconfigured."
        ),
    )
