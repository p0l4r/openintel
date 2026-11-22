"""SearXNG search + SSRF-safe page fetching + Trafilatura extraction."""
import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from .config import settings

MAX_BYTES = 2_000_000
MAX_REDIRECTS = 3
UA = "OpenIntelBot/0.1 (+research; respects robots via SearXNG results only)"


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def url_allowed(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.hostname) and _is_public_host(p.hostname)


log = logging.getLogger("openintel.search")


# ---- web search providers (each returns [{url, title, snippet}]) --------------------------------
async def _brave(q: str, n: int = 8) -> list[dict]:
    """Brave Search official API (needs BRAVE_API_KEY)."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://api.search.brave.com/res/v1/web/search",
                             params={"q": q, "count": n},
                             headers={"X-Subscription-Token": settings.brave_api_key, "Accept": "application/json"})
        r.raise_for_status()
    return [{"url": x["url"], "title": x.get("title", ""), "snippet": x.get("description", "")}
            for x in r.json().get("web", {}).get("results", [])[:n]]


async def _serper(q: str, n: int = 8) -> list[dict]:
    """Google results through the Serper API (needs SERPER_API_KEY)."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post("https://google.serper.dev/search", json={"q": q, "num": n},
                              headers={"X-API-KEY": settings.serper_api_key})
        r.raise_for_status()
    return [{"url": x["link"], "title": x.get("title", ""), "snippet": x.get("snippet", "")}
            for x in r.json().get("organic", [])[:n]]


async def _ddgs(q: str, n: int = 8) -> list[dict]:
    """DuckDuckGo through the `ddgs` library: no key needed, runs in a thread (it is synchronous)."""
    def run():
        from ddgs import DDGS
        return list(DDGS().text(q, max_results=n))
    rows = await asyncio.to_thread(run)
    return [{"url": r["href"], "title": r.get("title", ""), "snippet": r.get("body", "")} for r in rows]


async def web_search(query: str, n: int = 8) -> list[dict]:
    """Try providers in order and return the first non-empty answer. Keyed providers first (most
    reliable), then keyless DuckDuckGo, then the self-hosted SearXNG."""
    providers = []
    if settings.brave_api_key:
        providers.append(("brave", _brave))
    if settings.serper_api_key:
        providers.append(("serper", _serper))
    providers += [("ddgs", _ddgs), ("searxng", searx_search)]
    for name, fn in providers:
        try:
            res = await fn(query, n)
        except Exception as e:
            log.warning("search provider %s failed for %r: %s: %s", name, query, type(e).__name__, e)
            continue
        if res:
            return res
        log.warning("search provider %s returned no results for %r", name, query)
    return []


WIKI_API = "https://en.wikipedia.org/w/api.php"


async def spell_correct(query: str) -> str:
    """'Did you mean' via Wikipedia's search API. Returns the corrected query, or the original
    if no correction is offered (or the API is unreachable)."""
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": UA}) as client:
            r = await client.get(WIKI_API, params={
                "action": "query", "list": "search", "srsearch": query, "srlimit": 1,
                "srinfo": "suggestion|rewrittenquery", "srenablerewrites": 1, "format": "json"})
            r.raise_for_status()
            info = r.json().get("query", {}).get("searchinfo", {})
        fixed = (info.get("suggestion") or info.get("rewrittenquery") or "").strip()
        return fixed if 2 <= len(fixed) <= 200 else query
    except Exception:
        return query


async def wikipedia_pages(query: str, n: int = 3) -> list[dict]:
    """Layer 2 structured source: Wikipedia's official API (no scraping, no captcha, no key).
    Returns pages in the same shape as fetch_text()."""
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}) as client:
            r = await client.get(WIKI_API, params={"action": "query", "list": "search", "srsearch": query,
                                                   "srlimit": n, "format": "json"})
            r.raise_for_status()
            for hit in r.json()["query"]["search"]:
                r2 = await client.get(WIKI_API, params={
                    "action": "query", "prop": "extracts|info", "explaintext": 1, "redirects": 1,
                    "inprop": "url", "titles": hit["title"], "format": "json"})
                r2.raise_for_status()
                for page in r2.json()["query"]["pages"].values():
                    text = (page.get("extract") or "").strip()
                    if len(text) >= 200:
                        out.append({"url": page["fullurl"], "title": f"{page['title']} - Wikipedia",
                                    "published_at": None, "text": text[: settings.max_chars_per_source]})
    except Exception:
        pass
    return out


async def searx_search(query: str, n: int = 8) -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{settings.searxng_url}/search",
                             params={"q": query, "format": "json"})
        r.raise_for_status()
    return [{"url": x["url"], "title": x.get("title", ""), "snippet": x.get("content", "")}
            for x in r.json().get("results", [])[:n]]


async def fetch_text(url: str) -> dict | None:
    """Fetch with per-hop SSRF validation, size cap and timeout. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False,
                                     headers={"User-Agent": UA}) as client:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                # DNS check runs in a thread; revalidated on every redirect hop
                ok = await asyncio.to_thread(url_allowed, current)
                if not ok:
                    return None
                async with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        current = urljoin(current, resp.headers.get("location", ""))
                        continue
                    if resp.status_code != 200:
                        return None
                    if "html" not in resp.headers.get("content-type", "") and \
                            "text" not in resp.headers.get("content-type", ""):
                        return None
                    buf = b""
                    async for chunk in resp.aiter_bytes():
                        buf += chunk
                        if len(buf) > MAX_BYTES:
                            break
                    html = buf.decode(resp.encoding or "utf-8", errors="replace")
                    break
            else:
                return None
        text = trafilatura.extract(html, include_comments=False) or ""
        meta = trafilatura.extract_metadata(html)
        if len(text) < 200:
            return None
        return {
            "url": current,
            "title": (meta.title if meta else None) or "",
            "published_at": (meta.date if meta else None),
            "text": text[: settings.max_chars_per_source],
        }
    except Exception:
        return None
