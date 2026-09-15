"""Database engine and session management."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.config import get_database_path

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


def get_engine(echo: bool = False):
    """Create database engine."""
    db_path = get_database_path()
    
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use StaticPool for in-memory or file-based SQLite
    if str(db_path) == ":memory:":
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=echo
        )
    else:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=echo
        )
    
    # Enable foreign keys constraint
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    return engine


def get_session_factory(engine=None, echo: bool = False):
    """Create session factory."""
    if engine is None:
        engine = get_engine(echo=echo)
    
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Global engine and session factory
_engine = None
_session_factory = None


def get_db() -> Generator[Session, None, None]:
    """Get database session (FastAPI dependency)."""
    global _engine, _session_factory
    
    if _session_factory is None:
        _engine = get_engine()
        _session_factory = get_session_factory(_engine)
    
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


def init_db(echo: bool = False) -> None:
    """Initialize database tables."""
    global _engine, _session_factory
    
    _engine = get_engine(echo=echo)
    _session_factory = get_session_factory(_engine)
    
    # Import models to register them
    from app import models
    
    # Create all tables
    Base.metadata.create_all(bind=_engine)
    logger.info("Database initialized successfully")


def reset_db() -> None:
    """Reset database (for testing)."""
    global _engine, _session_factory
    
    _engine = None
    _session_factory = None
    
    # Re-initialize
    init_db()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database session (non-FastAPI usage)."""
    if _session_factory is None:
        init_db()
    
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()
