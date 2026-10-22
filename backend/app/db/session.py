"""SQLAlchemy engines for app / observer / remediator roles."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _make_engine(url: str, application_name: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"options": f"-c application_name={application_name}"},
    )


@lru_cache
def get_app_engine() -> Engine:
    return _make_engine(get_settings().database_url, "checkout_api")


@lru_cache
def get_observer_engine() -> Engine:
    return _make_engine(get_settings().observer_database_url, "recovery_observer")


@lru_cache
def get_executor_engine() -> Engine:
    return _make_engine(get_settings().executor_database_url, "recovery_remediator")


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(engine: Engine) -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
