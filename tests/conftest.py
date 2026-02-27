"""
Pytest Configuration and Shared Fixtures

This module provides pytest fixtures for testing the Financial Automation System.
Includes fixtures for database setup, FastAPI test client, and mock external services.

The test database is created fresh for each test session and cleaned up after tests.
External API services (Claude, Conta Azul, Autentique) are mocked to avoid hitting
real APIs during tests.
"""

import os
import pytest
from typing import Generator
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient


# ── Environment setup MUST come before any app imports ──────────────────────
# Settings() (via pydantic) validates required env vars at import time.
# API_SECRET_KEY has no default, so we must inject it before importing app code.
TEST_API_SECRET_KEY = os.getenv("API_SECRET_KEY", "test-secret-key-for-testing")
os.environ.setdefault("API_SECRET_KEY", TEST_API_SECRET_KEY)

# Signal to app code (e.g. lifespan) that we are running under pytest
os.environ["TESTING"] = "1"

# Provide dummy values for other required settings that lack defaults,
# so tests can import the app without a fully-populated .env file.
_REQUIRED_SETTINGS_DEFAULTS = {
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "CONTA_AZUL_CLIENT_ID": "test-client-id",
    "CONTA_AZUL_CLIENT_SECRET": "test-client-secret",
    "CONTA_AZUL_REDIRECT_URI": "http://localhost:8000/api/auth/conta-azul/callback",
    "AUTENTIQUE_API_KEY": "test-autentique-key",
}
for key, default in _REQUIRED_SETTINGS_DEFAULTS.items():
    os.environ.setdefault(key, default)

# Test database URL - use separate database for testing.
# Override with TEST_DATABASE_URL environment variable if provided.
# Default to SQLite so local test runs don't require a PostgreSQL role/database.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./tmp_test.db")

# ── Now safe to import app code (Settings will find all required vars) ──────
from app.database import Base, get_db
from app.main import app
from app.config import settings
import app.models as _app_models  # noqa: F401 - ensure all ORM models are registered in Base.metadata


def _cleanup_existing_tables(session: Session) -> None:
    """
    Delete rows only from tables that actually exist in the current database.

    This protects mixed local SQLite runs from intermittent `no such table`
    teardown/setup failures when metadata and physical schema drift.
    """
    inspector = inspect(session.bind)
    existing = set(inspector.get_table_names())
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in existing:
            session.execute(table.delete())


@pytest.fixture(scope="session")
def test_engine():
    """
    Create a test database engine for the entire test session.

    This engine is created once per test session and shared across all tests.
    The test database should be a separate database from the development database.

    Yields:
        Engine: SQLAlchemy engine connected to test database
    """
    engine_kwargs = {
        "pool_pre_ping": True,
        "echo": False,  # Set to True to see SQL queries during tests
    }
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine(TEST_DATABASE_URL, **engine_kwargs)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Drop all tables after test session
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """
    Create a fresh database session for each test function.

    We perform explicit table cleanup to guarantee isolation even when endpoint
    code calls ``session.commit()`` internally. This approach is deterministic
    across SQLite/PostgreSQL test environments.

    Args:
        test_engine: SQLAlchemy engine from test_engine fixture

    Yields:
        Session: SQLAlchemy database session for testing
    """
    # Ensure newly registered metadata tables are materialized before each test
    # (prevents intermittent "no such table" when import order changes).
    Base.metadata.create_all(bind=test_engine)

    session = Session(bind=test_engine)

    # Ensure clean start for every test function
    _cleanup_existing_tables(session)
    session.commit()

    try:
        yield session
    finally:
        session.rollback()
        _cleanup_existing_tables(session)
        session.commit()
        session.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI test client with test database dependency override.

    This fixture provides a TestClient for making API requests in tests.
    The database dependency is overridden to use the test database session.

    Args:
        db_session: Test database session from db_session fixture

    Yields:
        TestClient: FastAPI test client for API testing

    Usage:
        def test_create_client(client):
            response = client.post("/api/clients/", json={...})
            assert response.status_code == 201
    """
    # Override the get_db dependency to use test database
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session cleanup handled by db_session fixture

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, headers={"X-API-Key": TEST_API_SECRET_KEY}) as test_client:
        yield test_client

    # Clear dependency overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def mock_claude_response():
    """
    Mock response for Claude API calls.

    Returns a fixture that can be used to mock Claude API responses in tests.
    Useful for testing conversational flows without hitting the real Claude API.

    Returns:
        dict: Mock Claude API response data

    Usage:
        def test_conversation(mock_claude_response, monkeypatch):
            monkeypatch.setattr(
                "app.services.claude_service.ClaudeService.send_message",
                lambda *args, **kwargs: mock_claude_response
            )
            # Test code here
    """
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "Hello! I can help you collect information for a contract."
            }
        ],
        "model": "claude-sonnet-4-20250514",
        "stop_reason": "end_turn"
    }


@pytest.fixture
def mock_conta_azul_customer():
    """
    Mock Conta Azul customer data.

    Returns sample customer data in Conta Azul API format.
    Useful for testing Conta Azul integration without hitting real API.

    Returns:
        dict: Mock Conta Azul customer data
    """
    return {
        "id": "conta-azul-123",
        "name": "João Silva",
        "email": "joao.silva@example.com",
        "phone": "(11) 98765-4321",
        "person_type": "NATURAL",
        "document": "123.456.789-00",
        "address": {
            "street": "Rua Exemplo",
            "number": "123",
            "complement": "Apto 45",
            "zip_code": "01234-567",
            "neighborhood": "Centro",
            "city": "São Paulo",
            "state": "SP"
        }
    }


@pytest.fixture
def mock_autentique_document():
    """
    Mock Autentique document data.

    Returns sample document data in Autentique API format.
    Useful for testing Autentique integration without hitting real API.

    Returns:
        dict: Mock Autentique document data
    """
    return {
        "id": "autentique-doc-123",
        "name": "Contrato de Serviços - João Silva",
        "signatures": [
            {
                "public_id": "sig-123",
                "email": "joao.silva@example.com",
                "created_at": "2026-02-06T10:00:00Z",
                "signed": None,
                "rejected": None
            }
        ]
    }


@pytest.fixture
def sample_client_data():
    """
    Sample client data for creating test clients.

    Returns valid client data that can be used in POST requests to /api/clients/.

    Returns:
        dict: Sample client creation data
    """
    return {
        "name": "Maria Santos",
        "email": "maria.santos@example.com",
        "phone": "(21) 99876-5432",
        "cpf_cnpj": "987.654.321-00",
        "street": "Av. Paulista",
        "number": "1000",
        "complement": "Sala 100",
        "city": "São Paulo",
        "state": "SP",
        "zip_code": "01310-100",
        "notes": "Cliente preferencial"
    }


@pytest.fixture
def sample_contract_data():
    """
    Sample contract data for creating test contracts.

    Returns valid contract data that can be used in POST requests to /api/contracts/.

    Returns:
        dict: Sample contract creation data
    """
    return {
        "contract_number": "CTR-2026-001",
        "service_description": "Serviços de consultoria financeira",
        "contract_value": "5000.00",
        "payment_terms": "Mensal, vencimento dia 10",
        "start_date": "2026-03-01",
        "duration_months": 12,
        "special_clauses": "Reajuste anual pelo IPCA",
        "notes": "Contrato padrão de consultoria"
    }


@pytest.fixture
def sample_financial_record_data():
    """
    Sample financial record data for creating test records.

    Returns valid financial record data for testing.

    Returns:
        dict: Sample financial record creation data
    """
    return {
        "record_type": "receivable",
        "description": "Pagamento - Consultoria Março/2026",
        "amount": "5000.00",
        "due_date": "2026-03-10",
        "payment_date": None,
        "status": "pending",
        "category": "service_revenue",
        "notes": "Primeira parcela do contrato"
    }


# Pytest configuration
def pytest_configure(config):
    """
    Pytest configuration hook.

    Sets up custom markers and pytest configuration.
    """
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (may be slower)"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test (requires running services)"
    )


# Pytest asyncio configuration
@pytest.fixture(scope="session")
def event_loop():
    """
    Create an event loop for async tests.

    This fixture is required for pytest-asyncio to work properly.
    """
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
