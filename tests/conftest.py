"""Pytest configuration and fixtures."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test timezone
import os
os.environ.setdefault('TZ', 'Europe/Berlin')


@pytest.fixture
def sample_eml_homepage():
    """Sample homepage reservation email."""
    return Path(__file__).parent.parent / "samples" / "homepage_reservation.eml"


@pytest.fixture
def sample_eml_generic_external():
    """Sample generic external portal email."""
    return Path(__file__).parent.parent / "samples" / "generic_external_portal.eml"


@pytest.fixture
def sample_eml_invalid_window():
    """Sample email with invalid time window."""
    return Path(__file__).parent.parent / "samples" / "homepage_invalid_window.eml"


@pytest.fixture
def sample_eml_duplicate():
    """Sample duplicate reservation email."""
    return Path(__file__).parent.parent / "samples" / "duplicate_reservation.eml"


@pytest.fixture
def db_session():
    """Create a test database session."""
    from app.db import init_db, get_db_session, reset_db
    
    # Use in-memory database for tests
    import sqlalchemy
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    
    # Import models to register them
    from app import models
    from app.db import Base
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def reservation_repo(db_session):
    """Create reservation repository."""
    from app.repositories import ReservationRepository
    return ReservationRepository(db_session)


@pytest.fixture
def mail_log_repo(db_session):
    """Create mail log repository."""
    from app.repositories import MailLogRepository
    return MailLogRepository(db_session)


@pytest.fixture
def queue_repo(db_session):
    """Create parse queue repository."""
    from app.repositories import ParseQueueRepository
    return ParseQueueRepository(db_session)


@pytest.fixture
def parser_registry():
    """Create parser registry."""
    from app.parsers import ParserRegistry
    return ParserRegistry()
