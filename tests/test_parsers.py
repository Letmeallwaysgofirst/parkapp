"""Tests for email parsers."""

import pytest
from pathlib import Path

from app.parsers import ParserRegistry, parse_email_message, ParsedReservation
from app.parsers.normalizer import (
    normalize_license_plate,
    parse_datetime_explicit,
    split_name,
    check_valid_time_window
)
from datetime import datetime
from zoneinfo import ZoneInfo


class TestNormalizer:
    """Tests for normalizer functions."""
    
    def test_normalize_license_plate_basic(self):
        """Test basic plate normalization."""
        assert normalize_license_plate("abc123") == "ABC123"
        assert normalize_license_plate(" AB 123 ") == "AB123"
        assert normalize_license_plate("a-b-c-1-2-3") == "ABC123"
    
    def test_normalize_license_plate_with_umlauts(self):
        """Test German umlaut normalization."""
        assert normalize_license_plate("MÜ-MM-123") == "MUEMM123"
        assert normalize_license_plate("Österreich") == "OESTERREICH"
    
    def test_normalize_license_plate_none(self):
        """Test None input."""
        assert normalize_license_plate(None) is None
        assert normalize_license_plate("") is None
        assert normalize_license_plate("   ") is None
    
    def test_split_name_basic(self):
        """Test name splitting."""
        first, last = split_name("Max Mustermann")
        assert first == "Max"
        assert last == "Mustermann"
    
    def test_split_name_lastname_first(self):
        """Test name splitting with lastname first."""
        first, last = split_name("Mustermann, Max")
        assert first == "Max"
        assert last == "Mustermann"
    
    def test_split_name_single(self):
        """Test single name."""
        first, last = split_name("Max")
        assert first is None
        assert last == "Max"
    
    def test_split_name_none(self):
        """Test None input."""
        first, last = split_name(None)
        assert first is None
        assert last is None
    
    def test_check_valid_time_window(self):
        """Test time window validation."""
        tz = ZoneInfo("Europe/Berlin")
        valid_from = datetime(2026, 5, 11, 21, 45, tzinfo=tz)
        valid_until = datetime(2026, 5, 12, 8, 0, tzinfo=tz)
        
        assert check_valid_time_window(valid_from, valid_until) is True
        
        # Invalid window (until before from)
        invalid_until = datetime(2026, 5, 10, 8, 0, tzinfo=tz)
        assert check_valid_time_window(valid_from, invalid_until) is False
    
    def test_check_valid_time_window_none(self):
        """Test with None values."""
        assert check_valid_time_window(None, None) is True
        assert check_valid_time_window(datetime.now(), None) is True
        assert check_valid_time_window(None, datetime.now()) is True
    
    def test_parse_datetime_explicit(self):
        """Test explicit datetime parsing."""
        tz = "Europe/Berlin"
        
        dt = parse_datetime_explicit("2026-05-11", "21:45", "%Y-%m-%d", "%H:%M", tz)
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 11
        assert dt.hour == 21
        assert dt.minute == 45


class TestParserRegistry:
    """Tests for parser registry."""
    
    def test_detect_homepage_provider(self, parser_registry):
        """Test homepage provider detection."""
        body = """
        Neue Reservierungsanfrage von example-site.de
        Vorname / Nachname: Max Mustermann
        Kennzeichen: TGM515
        """
        
        provider = parser_registry.detect_provider(
            body=body,
            subject="Reservierungsanfrage für Caravan Stellplatz",
            sender="noreply@example-site.de",
            sender_domain="example-site.de"
        )
        
        assert provider == "HOMEPAGE"
    
    def test_detect_unknown_provider(self, parser_registry):
        """Test unknown provider detection."""
        body = """
        Some random email content
        that doesn't match any known pattern
        """
        
        provider = parser_registry.detect_provider(
            body=body,
            subject="Random Subject",
            sender="unknown@example.com",
            sender_domain="example.com"
        )
        
        assert provider == "UNKNOWN"
    
    def test_parse_homepage_reservation(self, parser_registry, sample_eml_homepage):
        """Test parsing homepage reservation email."""
        with open(sample_eml_homepage, 'r') as f:
            content = f.read()
        
        subject, sender, sender_domain, body = parse_email_message(content)
        
        result = parser_registry.parse(body, subject, sender, sender_domain)
        
        assert result.success is True
        assert result.provider == "HOMEPAGE"
        
        reservation = result.reservation
        assert reservation is not None
        assert reservation.plate_raw == "TGM515"
        assert reservation.plate_normalized == "TGM515"
        assert reservation.first_name == "Max"
        assert reservation.last_name == "Mustermann"
        assert reservation.email == "max.mustermann@example.com"
        assert reservation.valid_from is not None
        assert reservation.valid_until is not None
        assert reservation.incomplete_flag is False
    
    def test_parse_generic_external(self, parser_registry, sample_eml_generic_external):
        """Test parsing generic external portal email."""
        with open(sample_eml_generic_external, 'r') as f:
            content = f.read()
        
        subject, sender, sender_domain, body = parse_email_message(content)
        
        result = parser_registry.parse(body, subject, sender, sender_domain)
        
        assert result.success is True
        
        reservation = result.reservation
        assert reservation is not None
        assert reservation.plate_raw == "ABC123"
        assert reservation.plate_normalized == "ABC123"
        assert reservation.last_name == "John Doe"
        # Should be incomplete because no time window
        assert reservation.incomplete_flag is True
        assert reservation.valid_from is None
        assert reservation.valid_until is None
    
    def test_parse_email_extracts_body(self, sample_eml_homepage):
        """Test email parsing extracts correct fields."""
        with open(sample_eml_homepage, 'r') as f:
            content = f.read()
        
        subject, sender, sender_domain, body = parse_email_message(content)
        
        assert "Reservierungsanfrage" in subject
        assert "example-site.de" in sender
        assert "TGM515" in body
        assert "Max Mustermann" in body


class TestDuplicateDetection:
    """Tests for duplicate detection."""
    
    def test_message_id_duplicate(self, db_session, mail_log_repo, sample_eml_homepage):
        """Test duplicate message ID detection."""
        message_id = "<homepage-reservation-001@example-site.de>"
        
        # First call - not a duplicate
        assert mail_log_repo.is_duplicate_message(message_id) is False
        
        # Create first entry
        mail_log_repo.create(
            message_id=message_id,
            provider="HOMEPAGE",
            parse_ok=True
        )
        db_session.commit()
        
        # Second call - should be duplicate
        assert mail_log_repo.is_duplicate_message(message_id) is True
    
    def test_heuristic_duplicate(self, reservation_repo, db_session):
        """Test heuristic duplicate detection."""
        from app.parsers import ParsedReservation
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        tz = ZoneInfo("Europe/Berlin")
        
        # Create first reservation
        parsed1 = ParsedReservation(
            provider="HOMEPAGE",
            plate_raw="TGM515",
            plate_normalized="TGM515",
            valid_from=datetime(2026, 5, 11, 21, 45, tzinfo=tz),
            valid_until=datetime(2026, 5, 12, 8, 0, tzinfo=tz)
        )
        res1 = reservation_repo.create(parsed1)
        db_session.commit()
        
        # Check for heuristic duplicate - same plate, provider, overlapping window
        duplicate = reservation_repo.check_heuristic_duplicate(
            plate_normalized="TGM515",
            provider="HOMEPAGE",
            valid_from=datetime(2026, 5, 11, 22, 0, tzinfo=tz),
            valid_until=datetime(2026, 5, 12, 9, 0, tzinfo=tz)
        )
        
        assert duplicate is not None
        assert duplicate.id == res1.id


class TestInvalidWindow:
    """Tests for invalid time window detection."""
    
    def test_invalid_window_flagged(self, parser_registry, sample_eml_invalid_window):
        """Test that invalid time window is flagged."""
        with open(sample_eml_invalid_window, 'r') as f:
            content = f.read()
        
        subject, sender, sender_domain, body = parse_email_message(content)
        
        result = parser_registry.parse(body, subject, sender, sender_domain)
        
        assert result.success is True
        
        reservation = result.reservation
        assert reservation is not None
        # Time window should be invalid (bis before von)
        # Parser should detect this and set incomplete_flag
        assert reservation.incomplete_flag is True
        assert "Ungültiges Zeitfenster" in (reservation.notes or "")


class TestTimezone:
    """Tests for timezone handling."""
    
    def test_datetime_has_timezone(self, parser_registry, sample_eml_homepage):
        """Test that parsed datetimes have timezone."""
        with open(sample_eml_homepage, 'r') as f:
            content = f.read()
        
        subject, sender, sender_domain, body = parse_email_message(content)
        
        result = parser_registry.parse(body, subject, sender, sender_domain)
        
        reservation = result.reservation
        
        if reservation.valid_from:
            assert reservation.valid_from.tzinfo is not None
            assert str(reservation.valid_from.tzinfo) == "Europe/Berlin"
        
        if reservation.valid_until:
            assert reservation.valid_until.tzinfo is not None
            assert str(reservation.valid_until.tzinfo) == "Europe/Berlin"
