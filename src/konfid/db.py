from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

SCHEMA_HEAD = "e61c8a7d2f04"


class Base(DeclarativeBase):
    pass


def make_engine():
    s = get_settings()
    url = s.database_url
    kw: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
    else:
        kw.update(
            pool_size=s.database_pool_size,
            max_overflow=s.database_max_overflow,
            pool_timeout=s.database_pool_timeout_seconds,
            pool_recycle=s.database_pool_recycle_seconds,
        )
    engine = create_engine(url, **kw)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def pragmas(conn, _):
            c = conn.cursor()
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=5000")
            c.close()
    elif url.startswith("postgresql"):
        @event.listens_for(engine, "connect")
        def postgres_session_settings(conn, _):
            c = conn.cursor()
            c.execute(f"SET statement_timeout = {int(s.database_statement_timeout_ms)}")
            c.execute(f"SET lock_timeout = {int(s.database_lock_timeout_ms)}")
            c.execute(f"SET idle_in_transaction_session_timeout = {int(s.database_idle_in_transaction_timeout_ms)}")
            c.execute("SET timezone = 'UTC'")
            c.execute("SET application_name = 'konfid'")
            c.close()
    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)


def database_ready(*, require_head: bool | None = None) -> tuple[bool, str]:
    s = get_settings()
    if require_head is None:
        require_head = s.require_schema_head
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if require_head:
                row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
                if row != SCHEMA_HEAD:
                    return False, f"schema_not_at_head:{row or 'missing'}"
        return True, "ok"
    except Exception as exc:
        return False, f"database_unavailable:{type(exc).__name__}"
