# OpenIntel

Search an entity → 3 AI agents → sourced profile, timeline and clickable relationship graph.

**Stack (all open source):** FastAPI · SQLAlchemy (Postgres/SQLite) · SearXNG · Trafilatura · Ollama (any OpenAI-compatible LLM) · React + Vite · Cytoscape.js · ReportLab · NetworkX/Matplotlib. Self-hostable: no payment provider, no external account needed.

## Run
```bash
cp .env.example .env            # edit secrets
docker compose up --build
docker compose exec ollama ollama pull qwen2.5:3b
# UI: http://localhost:5173   API docs: http://localhost:8000/docs
```
Local dev without Docker: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload` (uses SQLite; needs a SearXNG + LLM endpoint, see `.env.example`).

## The three agents (`backend/app/agents/`)
1. **discovery** – LLM plans queries → SearXNG → SSRF-safe fetch → Trafilatura text.
2. **extraction** – per-page claim extraction. Every claim must carry a *verbatim excerpt*; claims whose excerpt isn't found in the page are dropped (anti-hallucination). Same claim in several sources → higher confidence.
3. **synthesis** – graph/timeline/facts are built *deterministically* from validated claims (no edge without evidence); the LLM only writes the summary. Uncorroborated links are labelled `candidate`; conflicting values are listed under limitations.

Intermediate outputs (sources, claims, result) are stored on the job row.

## Search limits (optional)
Limits are off by default, which suits a private self-hosted instance. To rate-limit a public instance, set these in `.env` (rolling window of `QUOTA_WINDOW_DAYS`, default 30; `0` = unlimited):

| Setting | Applies to |
|---|---|
| `GUEST_LIMIT` | anonymous visitors, per IP (hashed server-side) |
| `USER_LIMIT` | each registered account |

## Accounts and saved profiles
Registration is what keeps your work:
- **Signed in:** every profile is saved to your account. Searching the same entity again opens your saved profile instantly, without a new search and without using quota. Use **Refresh** on a profile to search again and replace it, and see all of them under *Account → Saved profiles*.
- **Not signed in:** profiles are not saved, so searching the same entity again runs the full search again. A profile made while signed out can be attached to a new account with **Save** after signing in.

Everything else (profile and graph PDFs, JSON API, API keys) is available to every signed-in user.

## Exports / API
- Profile PDF and Graph PDF (any logged-in user): `GET /api/v1/entities/{id}/export/{profile.pdf|graph.pdf}`
- JSON: `GET /api/v1/research/{id}/result`, `/entities/{id}/graph|timeline|sources`. API keys (created on the Account page) via header `X-API-Key`.
- Full docs at `/docs` (OpenAPI).

## Know shortcomings
- Jobs run in-process (FastAPI background task + semaphore). Move to Celery/Redis to survive restarts and scale out.
- Quota check uses a process-local lock; use Redis/DB row locking if running multiple workers.
- No Alembic migrations (tables auto-created), no email verification, no rate limiting on login, no CAPTCHA.
- Result/profile URLs are readable by anyone holding the unguessable job id (guest "public profile view").
- Small local models extract less reliably; use a bigger model or a hosted endpoint for quality.
- Target public figures and organizations. Respect site terms, copyright and data-protection law (e.g. GDPR) – publicly available is not the same as free to profile.
- Search is not full-proof yet. DuckDuckGo sometime can search the entity, sometimes it fails. I am working on it.
- Exporting graph pdf shows some issues, trying to fix it. However, exporting profile pdf works as intended.