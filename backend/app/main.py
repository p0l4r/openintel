import asyncio
import threading

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from . import pdf
from .config import settings
from .db import ApiKey, ResearchJob, SessionLocal, User, init_db
from .pipeline import run_job
from .security import (check_pw, client_ip, current_user, current_user_optional, hash_key, hash_pw,
                       ip_hash, make_token, new_api_key, quota_for, used_in_window)

app = FastAPI(title="OpenIntel API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_methods=["*"],
                   allow_headers=["*"])
_quota_lock = threading.Lock()  # single-process atomicity; use Redis/DB row lock when scaling out
_running = asyncio.Semaphore(2)  # global concurrency cap on research jobs


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/api/v1/health")
def health():
    return {"ok": True}


# ---------- auth ----------
class Creds(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


@app.post("/api/v1/auth/register")
def register(c: Creds):
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == c.email.lower())):
            raise HTTPException(409, "Email already registered")
        u = User(email=c.email.lower(), password_hash=hash_pw(c.password))
        db.add(u)
        db.commit()
        return {"token": make_token(u.id)}


@app.post("/api/v1/auth/login")
def login(c: Creds):
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == c.email.lower()))
        if not u or not check_pw(c.password, u.password_hash):
            raise HTTPException(401, "Invalid credentials")
        return {"token": make_token(u.id)}


@app.get("/api/v1/usage")
def usage(request: Request, user: User | None = Depends(current_user_optional)):
    with SessionLocal() as db:
        used = used_in_window(db, user, ip_hash(client_ip(request)))
    return {"email": user.email if user else None, "used": used, "limit": quota_for(user), "window_days": settings.quota_window_days}


# ---------- research ----------
class ResearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    context: str = Field(default="", max_length=300)
    refresh: bool = False  # signed-in users: ignore the saved profile and research again


async def _guarded_run(job_id, q, ctx):
    async with _running:
        await run_job(job_id, q, ctx)


@app.post("/api/v1/research", status_code=202)
def start_research(body: ResearchIn, request: Request, bg: BackgroundTasks,
                   user: User | None = Depends(current_user_optional)):
    iph = ip_hash(client_ip(request))
    q, ctx = body.query.strip(), body.context.strip()
    with _quota_lock, SessionLocal() as db:
        # Saved profiles belong to accounts: a signed-in user gets their own earlier result back instantly
        # (no quota, no compute) until they ask for a refresh. Guests have nothing saved, so every guest
        # search runs again.
        if user and not body.refresh:
            saved = db.scalar(select(ResearchJob).where(
                ResearchJob.owner_id == user.id, func.lower(ResearchJob.query) == q.lower(),
                ResearchJob.context == ctx, ResearchJob.status == "completed"
            ).order_by(ResearchJob.created_at.desc()))
            if saved:
                return {"job_id": saved.id, "status": "completed", "cached": True}
        used = used_in_window(db, user, iph)
        if quota_for(user) and used >= quota_for(user):  # 0 = unlimited
            raise HTTPException(429, detail={
                "code": "quota_exceeded", "used": used, "limit": quota_for(user),
                "message": "Search limit reached. Sign in for a higher limit, or ask the operator to raise it."
                if not user else "Search limit reached for this period. Ask the operator to raise it."})
        job = ResearchJob(owner_id=user.id if user else None, ip_hash=iph, query=q, context=ctx)
        db.add(job)
        db.commit()
        job_id = job.id
    bg.add_task(_guarded_run, job_id, q, ctx)
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/v1/research/{job_id}"}


def _job(job_id: str) -> ResearchJob:
    with SessionLocal() as db:
        j = db.get(ResearchJob, job_id)
    if not j:
        raise HTTPException(404, "Not found")
    return j


@app.get("/api/v1/research/{job_id}")
def job_status(job_id: str):
    j = _job(job_id)
    return {"job_id": j.id, "query": j.query, "status": j.status, "stage": j.stage, "error": j.error}


@app.get("/api/v1/research/{job_id}/result")
def job_result(job_id: str):
    j = _job(job_id)
    if j.status != "completed":
        raise HTTPException(409, f"Job is {j.status}")
    return j.result


@app.get("/api/v1/entities/{entity_id}")
def entity(entity_id: str):
    return job_result(entity_id)["profile"] | {"target_entity": job_result(entity_id)["target_entity"]}


@app.get("/api/v1/entities/{entity_id}/graph")
def entity_graph(entity_id: str):
    return job_result(entity_id)["graph"]


@app.get("/api/v1/entities/{entity_id}/timeline")
def entity_timeline(entity_id: str):
    return job_result(entity_id)["timeline"]


@app.get("/api/v1/entities/{entity_id}/sources")
def entity_sources(entity_id: str):
    return job_result(entity_id)["sources"]


@app.get("/api/v1/history")
def history(user: User = Depends(current_user)):
    """The user's saved profiles: the newest completed result per entity, plus anything still running."""
    with SessionLocal() as db:
        rows = db.scalars(select(ResearchJob).where(ResearchJob.owner_id == user.id)
                          .order_by(ResearchJob.created_at.desc()).limit(300)).all()
    seen, out = set(), []
    for j in rows:  # newest first
        if j.status == "failed":
            continue
        key = (j.query.lower(), j.context)
        if key in seen:
            continue
        seen.add(key)
        out.append({"job_id": j.id, "query": j.query, "status": j.status, "created_at": j.created_at})
    return out[:100]


@app.post("/api/v1/research/{job_id}/save")
def save_profile(job_id: str, user: User = Depends(current_user)):
    """Attach a profile that was made while signed out to the signed-in account."""
    with SessionLocal() as db:
        j = db.get(ResearchJob, job_id)
        if not j:
            raise HTTPException(404, "Not found")
        if j.owner_id and j.owner_id != user.id:
            raise HTTPException(403, "This profile belongs to another account")
        j.owner_id = user.id
        db.commit()
    return {"saved": True}


# ---------- exports (from saved result, no new research) ----------
@app.get("/api/v1/entities/{entity_id}/export/{kind}")
def export(entity_id: str, kind: str, user: User = Depends(current_user)):
    result = job_result(entity_id)
    if kind == "profile.pdf":
        data, mt = pdf.profile_pdf(result), "application/pdf"
    elif kind == "graph.pdf":
        data, mt = pdf.graph_pdf(result), "application/pdf"
    else:
        raise HTTPException(404, "Unknown export")
    return Response(data, media_type=mt,
                    headers={"Content-Disposition": f'attachment; filename="{kind}"'})


# ---------- api keys ----------
@app.post("/api/v1/api-keys")
def create_key(user: User = Depends(current_user)):
    raw = new_api_key()
    with SessionLocal() as db:
        k = ApiKey(user_id=user.id, key_hash=hash_key(raw), prefix=raw[:8])
        db.add(k)
        db.commit()
        return {"id": k.id, "key": raw, "note": "Shown once. Store it securely."}


@app.get("/api/v1/api-keys")
def list_keys(user: User = Depends(current_user)):
    with SessionLocal() as db:
        ks = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked == False)).all()  # noqa: E712
    return [{"id": k.id, "prefix": k.prefix, "created_at": k.created_at} for k in ks]


@app.delete("/api/v1/api-keys/{key_id}")
def revoke_key(key_id: str, user: User = Depends(current_user)):
    with SessionLocal() as db:
        k = db.get(ApiKey, key_id)
        if not k or k.user_id != user.id:
            raise HTTPException(404, "Not found")
        k.revoked = True
        db.commit()
    return {"revoked": True}
