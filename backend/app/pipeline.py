import asyncio

from .agents import discovery, extraction, synthesis
from .config import settings
from .db import ResearchJob, SessionLocal, now


def _update(job_id: str, **kw):
    with SessionLocal() as db:
        job = db.get(ResearchJob, job_id)
        for k, v in kw.items():
            setattr(job, k, v)
        db.commit()


async def _run(job_id: str, original: str, context: str):
    _update(job_id, status="running", stage="discover")
    sources, query = await discovery.run(original, context)  # query changes only if spelling was corrected
    if not sources:
        raise RuntimeError(f"No page mentioning '{original}' was found. Check the spelling, add more of the "
                           "name, or check that web search works (see README: search providers).")
    _update(job_id, sources=[{k: v for k, v in s.items() if k != "text"} for s in sources], stage="extract")
    claims = await extraction.run(query, sources)
    if not claims:
        raise RuntimeError("Sources were found but no relevant evidence could be extracted from them.")
    _update(job_id, claims=claims, stage="synthesize")
    result = await synthesis.run(job_id, query, claims, sources)
    result["metadata"]["original_query"] = original
    result["metadata"]["corrected_query"] = query if query.lower() != original.lower() else None
    _update(job_id, result=result, status="completed", stage="done", completed_at=now())


async def run_job(job_id: str, query: str, context: str):
    try:
        await asyncio.wait_for(_run(job_id, query, context), settings.job_timeout_s)
    except Exception as e:  # each stage failure is recorded
        _update(job_id, status="failed", error=f"{type(e).__name__}: {e}"[:500], completed_at=now())
