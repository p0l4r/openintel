"""Diagnostic: which search providers work from this machine?

    docker compose exec backend python -m app.search_check "Data Vantage GmbH"
"""
import asyncio
import sys

from .config import settings
from .fetcher import _brave, _ddgs, _serper, searx_search, wikipedia_pages


async def main(q: str):
    providers = [("ddgs (DuckDuckGo)", _ddgs), ("searxng", searx_search)]
    if settings.brave_api_key:
        providers.insert(0, ("brave api", _brave))
    if settings.serper_api_key:
        providers.insert(0, ("serper api", _serper))
    print(f"query: {q}")
    for name, fn in providers:
        try:
            rows = await fn(q, 8)
            print(f"  {name}: {len(rows)} results", [r["url"] for r in rows[:3]])
        except Exception as e:
            print(f"  {name}: ERROR {type(e).__name__}: {e}")
    pages = await wikipedia_pages(q)
    print(f"  wikipedia: {len(pages)} pages", [p["title"] for p in pages])
    if not settings.brave_api_key and not settings.serper_api_key:
        print("  (no BRAVE_API_KEY / SERPER_API_KEY set: keyed providers skipped)")


asyncio.run(main(" ".join(sys.argv[1:]) or "Data Vantage GmbH"))
