"""
Database Configuration and Session Management

This module provides SQLAlchemy database engine, session management, and
declarative base for ORM models. Uses connection pooling for efficient
database access and provides FastAPI dependency for request-scoped sessions.

All database models should inherit from the Base class defined here.
The engine is configured from the DATABASE_URL environment variable.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from app.config import settings

# Create database engine with connection pooling
# pool_pre_ping=True ensures connections are alive before using them
# echo=True in debug mode for SQL query logging
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
    pool_size=5,  # Maximum number of connections to keep in pool
    max_overflow=10  # Maximum overflow connections beyond pool_size
)

# Create session factory
# autocommit=False: transactions must be explicitly committed
# autoflush=False: manual control over when to flush changes
# bind=engine: associate sessions with our database engine
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Declarative base class for all ORM models
# All database models should inherit from this class
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database session management.

    Provides a request-scoped database session that is automatically
    closed after the request completes. Use this as a dependency in
    API endpoints to get a database session.

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()

    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
