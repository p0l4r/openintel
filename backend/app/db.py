import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String)
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    ip_hash: Mapped[str] = mapped_column(String, index=True)
    query: Mapped[str] = mapped_column(String, index=True)
    context: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|running|completed|failed
    stage: Mapped[str] = mapped_column(String, default="queued")  # discover|extract|synthesize
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # persisted intermediate agent outputs (resumable / auditable)
    sources: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    claims: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def init_db():
    Base.metadata.create_all(engine)
    _drop_legacy_columns()


def _drop_legacy_columns():
    """Databases created before payments were removed still have NOT NULL billing columns that new
    inserts would violate. Drop them once; harmless if already gone."""
    from sqlalchemy import inspect, text
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        for col in ("plan", "stripe_customer_id"):
            if col in cols:
                try:
                    conn.execute(text(f"ALTER TABLE users DROP COLUMN {col}"))
                except Exception:
                    pass
