"""Engine and session factory.

Default: a SQLite file under ./data. Set DATABASE_URL for Postgres
(Supabase). The schema in models.py is the same in both cases.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_SQLITE = f"sqlite:///{DATA_DIR / 'copilot.db'}"


def make_engine(url: str | None = None):
    url = url or os.getenv("DATABASE_URL") or DEFAULT_SQLITE
    if url.startswith("sqlite"):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(url), expire_on_commit=False)
