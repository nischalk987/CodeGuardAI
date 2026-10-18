import os
import re
import uuid
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.infrastructure.persistence.database import get_session
from app.main import create_app


@pytest.fixture
def migrated_database():
    """Create a fresh isolated SQLite database by applying the production migrations."""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


@pytest.fixture
def review_client(
    migrated_database: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    test_app = create_app(Settings(_env_file=None, environment="test"))

    def override_session() -> Generator[Session, None, None]:
        with migrated_database() as session:
            yield session

    test_app.dependency_overrides[get_session] = override_session

    monkeypatch.setattr("app.api.v1.reviews.enqueue_review_task", lambda *_args: None)
    test_app.state.review_session_factory = migrated_database
    with TestClient(test_app) as client:
        yield client


@pytest.fixture
def run_queued_review():
    """Execute a queued test request only after its HTTP session has been returned."""
    def run(factory, review_id: str, request_data: dict[str, str]) -> None:
        from app.application.reviews import ReviewService
        from app.infrastructure.persistence.repository import SqlAlchemyReviewRepository
        from app.schemas import ReviewCreateRequest

        with factory() as session:
            ReviewService(SqlAlchemyReviewRepository(session)).execute_queued(
                review_id, ReviewCreateRequest.model_validate(request_data)
            )

    return run


@pytest.fixture
def postgres_review_client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    """Run API integration checks in a unique schema on a disposable PostgreSQL database."""
    database_url = os.getenv("CODEGUARD_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("CODEGUARD_TEST_DATABASE_URL is not configured")

    schema = f"codeguard_it_{uuid.uuid4().hex}"
    if not re.fullmatch(r"codeguard_it_[a-f0-9]{32}", schema):
        pytest.fail("Invalid generated PostgreSQL test schema name")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=5000"},
    )
    schema_created = False

    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True

        @event.listens_for(engine, "connect")
        def set_test_schema(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute(f'SET search_path TO "{schema}"')
            cursor.close()

        with engine.begin() as connection:
            connection.execute(text(f'SET search_path TO "{schema}"'))
            current_schema = connection.scalar(text("select current_schema()"))
            if current_schema != schema:
                raise RuntimeError("PostgreSQL test schema was not selected")
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    except Exception as exc:
        if schema_created:
            try:
                with engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            except Exception:
                pass
        engine.dispose()
        pytest.fail(f"PostgreSQL test setup failed ({type(exc).__name__}); details suppressed")

    test_app = create_app(Settings(_env_file=None, environment="test"))
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    test_app.dependency_overrides[get_session] = override_session

    monkeypatch.setattr("app.api.v1.reviews.enqueue_review_task", lambda *_args: None)
    test_app.state.review_session_factory = factory
    try:
        with TestClient(test_app) as client:
            yield client
    finally:
        try:
            if schema_created:
                with engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        except Exception:
            # Cleanup failures are not allowed to print connection details or values.
            pytest.fail("PostgreSQL test schema cleanup failed; details suppressed")
        finally:
            engine.dispose()
