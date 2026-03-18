"""
SQLAlchemy engine, session factory, and FastAPI dependency for database access.
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.loader import get_config
from app.db.models import Base

# ---------------------------------------------------------------------------
# Engine and session factory — created lazily on first import so that
# get_config() can be called after the config file has been placed.
# ---------------------------------------------------------------------------

def _build_engine():
    cfg = get_config()
    db_url = cfg.database.url
    connect_args = {}
    if db_url.startswith("sqlite"):
        # SQLite requires check_same_thread=False when used with FastAPI
        connect_args = {"check_same_thread": False}
    return create_engine(db_url, connect_args=connect_args, future=True)


# Module-level singletons (lazy)
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine()
        )
    return _SessionLocal


# Convenience alias
def SessionLocal() -> Session:  # type: ignore[return]
    return get_session_local()()


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=get_engine())


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session and ensures it is
    closed after the request completes.

    Usage::

        @router.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()
