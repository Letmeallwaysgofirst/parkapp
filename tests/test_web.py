"""Tests for web UI."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.web.routes import app
from app.db import Base, get_db


TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def client():
    """Create test client with test database."""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    
    TestingSessionLocal = sessionmaker(bind=engine)
    
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    client = TestClient(app)
    
    yield client
    
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


class TestLogin:
    """Tests for login functionality."""
    
    def test_login_page_loads(self, client):
        """Test login page loads."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "Anmeldung" in response.text
    
    def test_login_requires_password(self, client):
        """Test login requires password."""
        response = client.post("/login", data={"password": "wrong"})
        assert response.status_code == 200
        assert "Falsches Passwort" in response.text


class TestDashboard:
    """Tests for dashboard page."""
    
    def test_dashboard_requires_login(self, client):
        """Test dashboard requires login."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code in [302, 303]
        assert "/login" in response.headers.get("location", "")


class TestArchive:
    """Tests for archive page."""
    
    def test_archive_requires_login(self, client):
        """Test archive requires login."""
        response = client.get("/archiv", follow_redirects=False)
        assert response.status_code in [302, 303]


class TestKlaerungsfaelle:
    """Tests for clarification queue page."""
    
    def test_queue_requires_login(self, client):
        """Test queue requires login."""
        response = client.get("/klärungsfälle", follow_redirects=False)
        assert response.status_code in [302, 303]


class TestReservationForm:
    """Tests for reservation form."""
    
    def test_new_reservation_requires_login(self, client):
        """Test new reservation form requires login."""
        response = client.get("/reservierung/Neu", follow_redirects=False)
        assert response.status_code in [302, 303]


class TestCSVExport:
    """Tests for CSV export."""
    
    def test_export_requires_login(self, client):
        """Test CSV export requires login."""
        response = client.get("/archiv/export", follow_redirects=False)
        assert response.status_code in [302, 303]


class TestSafeMailDisplay:
    """Tests for safe mail content display."""
    
    def test_queue_mail_requires_auth(self, client):
        """Test mail content endpoint requires authentication (returns 401)."""
        response = client.get("/klärungsfälle/mail/1")
        # API endpoint returns 401 when not authenticated
        assert response.status_code == 401
