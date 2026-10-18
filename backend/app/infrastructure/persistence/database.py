"""Safe SQLAlchemy engine and session management."""

from collections.abc import Generator
from threading import Lock

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


class DatabaseNotConfigured(RuntimeError):
    """Raised when persistent endpoints are used without DATABASE_URL."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_engine_lock = Lock()


def _database_url() -> URL:
    configured = get_settings().database_url
    if configured is None or not configured.get_secret_value().strip():
        raise DatabaseNotConfigured("DATABASE_URL is not configured")
    try:
        url = make_url(configured.get_secret_value())
    except (TypeError, ValueError):
        raise DatabaseNotConfigured("DATABASE_URL is invalid") from None
    if url.get_backend_name() == "sqlite":
        if get_settings().environment != "test":
            raise DatabaseNotConfigured("SQLite is available only in the test environment")
        return url
    if url.get_backend_name() != "postgresql" or not url.host or not url.database:
        raise DatabaseNotConfigured("DATABASE_URL must point to PostgreSQL")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                url = _database_url()
                options = {"pool_pre_ping": True, "pool_recycle": 300}
                if url.get_backend_name() == "postgresql":
                    options.update(
                        pool_size=5,
                        max_overflow=5,
                        pool_timeout=5,
                        connect_args={
                            "connect_timeout": 5,
                            "options": "-c statement_timeout=5000",
                        },
                    )
                _engine = create_engine(url, **options)
                _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session() -> Generator[Session, None, None]:
    get_engine()
    assert _session_factory is not None
    with _session_factory() as session:
        yield session


def reset_engine() -> None:
    """Dispose the cached engine; intended for test cleanup and process shutdown."""
    global _engine, _session_factory
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None
