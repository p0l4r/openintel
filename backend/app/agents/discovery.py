"""Agent 1 - Discover: plan queries, search the web, fetch + clean pages, and keep only pages that
actually mention the target. If nothing relevant is found, retry once with a spell-corrected name."""
import asyncio
import hashlib
import re
from datetime import datetime, timezone

from rapidfuzz import fuzz

from ..config import settings
from ..fetcher import fetch_text, spell_correct, web_search, wikipedia_pages
from ..llm import generate_json

SYSTEM = (
    "You plan web searches for researching a public entity. Return JSON: "
    '{"queries": ["..."]}. Queries must be short, varied (official site, background, '
    "history, partners/people, news). Never include private data lookups."
)

# legal-form words are ignored when checking that a page is about the target
LEGAL = {"gmbh", "ag", "ug", "kg", "ohg", "gbr", "mbh", "ev", "se", "ltd", "limited", "inc", "llc",
         "corp", "co", "sa", "bv", "plc", "oy", "ab", "srl", "spa"}
GERMAN_FORMS = {"gmbh", "ag", "ug", "kg", "ohg", "gbr", "mbh", "ev", "se"}


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s).lower().strip()


def _core(name: str) -> str:
    tokens = [t for t in _norm(name).split() if t not in LEGAL]
    return " ".join(tokens) or _norm(name)


def _mentions(name: str, title: str, text: str) -> bool:
    """Relevance gate: the page must contain the target's name (typos tolerated, but 'Data Vantage'
    does NOT match 'Data Voltage'). This is what stops look-alike entities from being researched."""
    return fuzz.partial_ratio(_core(name), _norm(f"{title} {text[:40000]}")) >= 90


def _base_queries(name: str, context: str) -> list[str]:
    ctx = f" {context}" if context else ""
    qs = [f'"{name}"{ctx}', f"{name}{ctx} about", f"{name}{ctx} news"]
    if set(_norm(name).split()) & GERMAN_FORMS:
        # German companies publish owners, address and registry number in the legal notice
        qs += [f'"{name}" Impressum', f'"{name}" Handelsregister Geschäftsführer']
    return qs


async def _collect(name: str, context: str) -> list[dict]:
    queries = _base_queries(name, context)
    try:
        plan = await generate_json(SYSTEM, f"Entity: {name}\nContext: {context}\n"
                                           f"Max queries: {settings.max_queries}")
        queries += [q for q in plan.get("queries", []) if isinstance(q, str)]
    except Exception:
        pass
    queries = list(dict.fromkeys(queries))[: settings.max_queries]

    results = []
    for q in queries:  # sequential + pause: search providers throttle bursts from one IP
        results.append(await web_search(q))
        await asyncio.sleep(1.0)

    seen, candidates = set(), []
    for res in results:
        for item in res:
            if item["url"] not in seen and len(candidates) < settings.max_urls:
                seen.add(item["url"])
                candidates.append(item)

    wiki = await wikipedia_pages(f"{name} {context}".strip())
    wiki_urls = {w["url"] for w in wiki}
    candidates = [c for c in candidates if c["url"] not in wiki_urls]
    web = await asyncio.gather(*(fetch_text(c["url"]) for c in candidates[: settings.max_pages * 2]))
    # reliable Wikipedia pages first, then web pages
    pairs = [({"title": w["title"]}, w) for w in wiki] + list(zip(candidates, web))

    sources = []
    for cand, page in pairs:
        if not page or len(sources) >= settings.max_pages:
            continue
        title = page["title"] or cand["title"]
        if not _mentions(name, title, page["text"]):
            continue  # unrelated page (look-alike name, generic result): discard
        sources.append({
            "id": f"s{len(sources) + 1}",
            "url": page["url"],
            "title": title,
            "published_at": page["published_at"],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": hashlib.sha256(page["text"].encode()).hexdigest(),
            "text": page["text"],
        })
    return sources


async def run(query: str, context: str) -> tuple[list[dict], str]:
    """Returns (sources, query_actually_used). The query is only changed by spell correction, and only
    when the original spelling produced no page that mentions it."""
    sources = await _collect(query, context)
    if sources:
        return sources, query
    fixed = await spell_correct(query)
    if fixed.lower() != query.lower():
        sources = await _collect(fixed, context)
        if sources:
            return sources, fixed
    return [], query
