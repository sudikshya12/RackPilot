from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            # Let SQLAlchemy manage transactions explicitly so we can issue BEGIN IMMEDIATE.
            dbapi_conn.isolation_level = None
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

        @event.listens_for(engine, "begin")
        def _sqlite_begin(conn):  # pragma: no cover - trivial
            # Write sessions take the write lock up front (serializes stock checks + writes);
            # read sessions use a deferred transaction so they never block writers (WAL).
            if conn.get_execution_options().get("sqlite_immediate"):
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.exec_driver_sql("BEGIN")

    return engine


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def configure(url: str):
    """Rebind the engine (used by tests)."""
    global engine
    engine = _make_engine(url)
    SessionLocal.configure(bind=engine)
    return engine


def write_session() -> Session:
    """A session whose transaction starts with BEGIN IMMEDIATE."""
    db = SessionLocal()
    db.connection(execution_options={"sqlite_immediate": True})
    return db


def get_write_db() -> Iterator[Session]:
    db = write_session()
    try:
        yield db
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
