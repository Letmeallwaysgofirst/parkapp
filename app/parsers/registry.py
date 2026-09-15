"""Parser registry for detecting and parsing parking reservation emails."""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable
from email import message_from_string
from email.policy import default as email_policy

from app.config import load_providers_config, get_configured_timezone
from app.parsers.normalizer import (
    normalize_license_plate, 
    parse_datetime_explicit,
    parse_datetime_combined,
    split_name,
    check_valid_time_window
)

logger = logging.getLogger(__name__)


@dataclass
class ParsedReservation:
    """Result of parsing a reservation email."""
    provider: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    plate_raw: Optional[str] = None
    plate_normalized: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    booked_at: Optional[datetime] = None
    voucher_code: Optional[str] = None
    external_reservation_id: Optional[str] = None
    incomplete_flag: bool = False
    notes: Optional[str] = None
    
    # Internal tracking
    source_message_id: Optional[str] = None
    source_mail_path: Optional[str] = None


@dataclass
class ParseResult:
    """Result of parsing attempt."""
    success: bool
    provider: str = "UNKNOWN"
    reservation: Optional[ParsedReservation] = None
    error_message: Optional[str] = None
    queued_reason: Optional[str] = None


class BaseParser:
    """Base parser class."""
    
    def __init__(self, config: dict, timezone: str = "Europe/Berlin"):
        self.config = config
        self.timezone = timezone
    
    def extract_value_after_marker(self, body: str, marker: str, strip: bool = True) -> Optional[str]:
        """Extract value after a marker line in text body."""
        for line in body.split('\n'):
            if marker in line:
                # Get everything after the marker
                value = line.split(marker, 1)[1].strip()
                # Remove leading separators like ':'
                value = re.sub(r'^[\s:]+', '', value).strip()
                return value if value else None
        return None
    
    def extract_value(self, body: str, key: str, strip: bool = True) -> Optional[str]:
        """Extract value by key from key-value lines."""
        pattern = rf'^{re.escape(key)}[:\s]*(.*)$'
        for line in body.split('\n'):
            match = re.match(pattern, line.strip(), re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value if (not strip or value) else None
        return None
    
    def split_value(self, body: str, key: str, delimiter: str = None, index: int = 0) -> Optional[str]:
        """Extract and split a value by key."""
        value = self.extract_value(body, key)
        if not value:
            return None
        
        if delimiter is None:
            parts = value.split()
        else:
            parts = value.split(delimiter)
        
        if index < len(parts):
            return parts[index].strip()
        return None
    
    def apply_datetime_config(
        self, 
        body: str, 
        datetime_config: dict
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Apply datetime configuration to extract valid_from and valid_until."""
        valid_from = None
        valid_until = None
        
        for target_field, config in datetime_config.items():
            if target_field == 'booked_at':
                # Handle booked_at separately
                continue
                
            date_source = config.get('date_source')
            date_format = config.get('date_format', '%Y-%m-%d')
            time_source = config.get('time_source')
            time_format = config.get('time_format', '%H:%M')
            combine = config.get('combine', 'append')
            
            date_str = self.extract_value(body, date_source) if date_source else None
            time_str = self.extract_value(body, time_source) if time_source else None
            
            if date_str:
                dt = parse_datetime_explicit(date_str, time_str, date_format, time_format, self.timezone)
                if target_field == 'valid_from':
                    valid_from = dt
                elif target_field == 'valid_until':
                    valid_until = dt
        
        return valid_from, valid_until
    
    def apply_field_mappings(self, body: str, mappings: list) -> dict:
        """Apply field mappings to extract values from body."""
        result = {}
        
        for mapping in mappings:
            target = mapping.get('target')
            source_type = mapping.get('source_type')
            
            if source_type == 'value':
                key = mapping.get('key')
                value = self.extract_value(body, key, strip=mapping.get('strip', True))
                
                # Handle empty/null values
                if value is None and not mapping.get('allow_empty', False):
                    continue
                if value == '' and mapping.get('null_if_empty', False):
                    value = None
                    
                result[target] = value
                
            elif source_type == 'value_after_marker':
                marker = mapping.get('marker')
                value = self.extract_value_after_marker(body, marker, strip=mapping.get('strip', True))
                
                if value is None and not mapping.get('allow_empty', False):
                    continue
                if value == '' and mapping.get('null_if_empty', False):
                    value = None
                    
                result[target] = value
                
            elif source_type == 'split':
                key = mapping.get('source')
                index = mapping.get('split_index', 0)
                value = self.split_value(body, key, index=index)
                result[target] = value
        
        return result
    
    def parse(self, body: str, subject: str = "", sender: str = "") -> Optional[ParsedReservation]:
        """Parse reservation data from email body."""
        raise NotImplementedError("Subclasses must implement parse()")


class HomepageParser(BaseParser):
    """Parser for homepage reservation emails."""
    
    def parse(self, body: str, subject: str = "", sender: str = "") -> ParsedReservation:
        result = ParsedReservation(provider="HOMEPAGE")
        
        # Apply field mappings
        mappings = self.config.get('extraction', {}).get('field_mappings', [])
        field_data = self.apply_field_mappings(body, mappings)
        
        # Set basic fields
        result.first_name = field_data.get('first_name')
        result.last_name = field_data.get('last_name')
        result.email = field_data.get('email')
        result.plate_raw = field_data.get('plate_raw')
        result.plate_normalized = normalize_license_plate(result.plate_raw)
        result.voucher_code = field_data.get('voucher_code')
        
        # Parse datetime
        datetime_config = self.config.get('datetime', {})
        valid_from, valid_until = self.apply_datetime_config(body, datetime_config)
        result.valid_from = valid_from
        result.valid_until = valid_until
        
        # Check time window validity
        if valid_from and valid_until:
            if not check_valid_time_window(valid_from, valid_until):
                result.incomplete_flag = True
                result.notes = f"Ungültiges Zeitfenster: valid_from={valid_from}, valid_until={valid_until}"
        
        return result


class GenericExternalParser(BaseParser):
    """Parser for generic external portal emails."""
    
    def parse(self, body: str, subject: str = "", sender: str = "") -> ParsedReservation:
        result = ParsedReservation(provider="UNKNOWN")  # Will be set by registry
        
        # Apply field mappings
        mappings = self.config.get('extraction', {}).get('field_mappings', [])
        field_data = self.apply_field_mappings(body, mappings)
        
        # Set basic fields - plate is required
        result.plate_raw = field_data.get('plate_raw')
        result.plate_normalized = normalize_license_plate(result.plate_raw)
        result.last_name = field_data.get('last_name')  # "Name des Fahrers"
        
        # booked_at is the booking timestamp, NOT the stay window
        booked_at_str = field_data.get('booked_at')
        if booked_at_str:
            # The booked_at format is already parsed by apply_field_mappings using format from config
            # We need to re-parse it here
            datetime_config = self.config.get('datetime', {})
            booked_format = datetime_config.get('booked_at', {}).get('format', '%d/%m/%Y %H:%M')
            result.booked_at = parse_datetime_combined(booked_at_str, booked_format, self.timezone)
        
        # Mark as incomplete since we don't have the stay window
        special_flags = self.config.get('special_flags', {})
        if special_flags.get('incomplete_data'):
            result.incomplete_flag = True
            result.notes = "Kein Zeitfenster in der E-Mail vorhanden. Zeitfenster muss manuell ergänzt werden."
        
        return result


# Registry of available parsers
PARSERS = {
    'HOMEPAGE': HomepageParser,
    'GENERIC_EXTERNAL': GenericExternalParser,
}


class ParserRegistry:
    """Registry for detecting providers and parsing emails."""
    
    def __init__(self, providers_config: dict = None):
        if providers_config is None:
            providers_config = load_providers_config()
        
        self.providers_config = providers_config.get('providers', {})
        self.timezone = get_configured_timezone()
        
        # Create parser instances
        self.parsers = {}
        for provider_name, provider_config in self.providers_config.items():
            parser_class = PARSERS.get(provider_name)
            if parser_class:
                self.parsers[provider_name] = parser_class(provider_config, self.timezone)
    
    def detect_provider(
        self, 
        body: str, 
        subject: str, 
        sender: str, 
        sender_domain: str = ""
    ) -> str:
        """Detect provider from email using configured rules."""
        
        for provider_name, provider_config in self.providers_config.items():
            detection = provider_config.get('detection', {})
            rules = detection.get('rules', [])
            
            for rule in rules:
                rule_type = rule.get('type')
                pattern = rule.get('pattern')
                flags = rule.get('flags', '')
                
                match = False
                
                if rule_type == 'subject':
                    match = bool(re.search(pattern, subject, re.IGNORECASE if 'i' in flags else 0))
                elif rule_type == 'body_marker':
                    match = pattern.lower() in body.lower()
                elif rule_type == 'sender_domain':
                    match = bool(re.search(pattern, sender_domain, re.IGNORECASE if 'i' in flags else 0))
                elif rule_type == 'sender':
                    match = bool(re.search(pattern, sender, re.IGNORECASE if 'i' in flags else 0))
                
                if match:
                    # Check if this is a generic/placeholder provider
                    if provider_name in ('KRAVAG', 'TRUCKS_NB', 'SNAP', 'GENERIC_EXTERNAL'):
                        if provider_name == 'GENERIC_EXTERNAL':
                            return provider_name  # Return as UNKNOWN provider, but mark in parsing
                        return 'UNKNOWN'  # TODO providers need real parser configs
                    return provider_name
        
        return 'UNKNOWN'
    
    def parse(
        self, 
        body: str, 
        subject: str = "", 
        sender: str = "",
        sender_domain: str = ""
    ) -> ParseResult:
        """Parse email and return result."""
        
        # Detect provider
        detected_provider = self.detect_provider(body, subject, sender, sender_domain)
        
        # Get parser
        parser = self.parsers.get(detected_provider)
        
        if parser is None:
            return ParseResult(
                success=False,
                provider=detected_provider,
                queued_reason='UNKNOWN_PROVIDER',
                error_message=f"No parser available for provider: {detected_provider}"
            )
        
        try:
            reservation = parser.parse(body, subject, sender)
            
            if reservation:
                reservation.provider = detected_provider if detected_provider != 'GENERIC_EXTERNAL' else 'UNKNOWN'
                
                return ParseResult(
                    success=True,
                    provider=detected_provider,
                    reservation=reservation
                )
            else:
                return ParseResult(
                    success=False,
                    provider=detected_provider,
                    queued_reason='PARSE_FAILED',
                    error_message="Parser returned no reservation data"
                )
                
        except Exception as e:
            logger.exception(f"Parse error for provider {detected_provider}")
            return ParseResult(
                success=False,
                provider=detected_provider,
                queued_reason='PARSE_FAILED',
                error_message=str(e)
            )


def parse_email_message(raw_content: str) -> tuple[str, str, str, str]:
    """
    Parse raw email content and extract key fields.
    
    Returns:
        Tuple of (subject, sender, sender_domain, body)
    """
    msg = message_from_string(raw_content, policy=email_policy)
    
    # Get subject
    subject = msg.get('subject', '')
    
    # Get sender
    sender = msg.get('from', '')
    
    # Extract sender domain
    sender_domain = ''
    if '<' in sender:
        email_match = re.search(r'<([^>]+)>', sender)
        if email_match:
            email = email_match.group(1)
            sender_domain = email.split('@')[1] if '@' in email else ''
    else:
        sender_domain = sender.split('@')[1] if '@' in sender else ''
    
    # Get body (prefer plain text)
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode('utf-8', errors='replace')
                        break
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode('utf-8', errors='replace')
        except Exception:
            body = str(msg.get_payload())
    
    return subject.strip(), sender.strip(), sender_domain.strip(), body.strip()
