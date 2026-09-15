"""License plate and data normalization utilities."""

import re
import unicodedata
from datetime import datetime
from typing import Optional, Tuple


def normalize_license_plate(plate: Optional[str]) -> Optional[str]:
    """
    Normalize a license plate for tolerant searching.
    
    - Convert to uppercase
    - Remove spaces, dashes, dots
    - Convert German umlauts to their ASCII equivalents
    - Strip extra whitespace
    
    Args:
        plate: Raw license plate string
        
    Returns:
        Normalized license plate or None if input is empty
    """
    if not plate:
        return None
    
    # Strip and uppercase
    normalized = plate.strip().upper()
    
    # Remove spaces, dashes, dots
    normalized = re.sub(r'[\s\-\.]+', '', normalized)
    
    # Convert German umlauts
    umlaut_map = {
        'Ä': 'AE',
        'Ö': 'OE',
        'Ü': 'UE',
        'Ä': 'AE',
        'Ø': 'OE',
        'Å': 'AA',
    }
    for umlaut, replacement in umlaut_map.items():
        normalized = normalized.replace(umlaut, replacement)
    
    # Normalize unicode characters
    normalized = unicodedata.normalize('NFKD', normalized)
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    
    return normalized if normalized else None


def parse_datetime_explicit(
    date_str: Optional[str],
    time_str: Optional[str],
    date_format: str,
    time_format: str,
    timezone_str: str = "Europe/Berlin"
) -> Optional[datetime]:
    """
    Parse datetime from separate date and time strings using explicit formats.
    
    Args:
        date_str: Date string
        time_str: Time string
        date_format: strftime format for date
        time_format: strftime format for time
        timezone_str: Timezone string
        
    Returns:
        Timezone-aware datetime or None if parsing fails
    """
    import zoneinfo
    
    if not date_str:
        return None
    
    # Parse date
    try:
        date_dt = datetime.strptime(date_str.strip(), date_format)
    except ValueError as e:
        raise ValueError(f"Failed to parse date '{date_str}' with format '{date_format}': {e}")
    
    # Parse time if provided
    if time_str:
        try:
            time_dt = datetime.strptime(time_str.strip(), time_format)
        except ValueError as e:
            raise ValueError(f"Failed to parse time '{time_str}' with format '{time_format}': {e}")
        
        # Combine date and time
        combined = date_dt.replace(
            hour=time_dt.hour,
            minute=time_dt.minute,
            second=time_dt.second if hasattr(time_dt, 'second') else 0,
            microsecond=0
        )
    else:
        combined = date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Localize to timezone
    try:
        tz = zoneinfo.ZoneInfo(timezone_str)
        combined = combined.replace(tzinfo=tz)
    except Exception:
        # Fallback to UTC if timezone is invalid
        combined = combined.replace(tzinfo=None)
    
    return combined


def parse_datetime_combined(
    datetime_str: Optional[str],
    datetime_format: str,
    timezone_str: str = "Europe/Berlin"
) -> Optional[datetime]:
    """
    Parse datetime from a combined string using explicit format.
    
    Args:
        datetime_str: Combined datetime string
        datetime_format: strftime format
        timezone_str: Timezone string
        
    Returns:
        Timezone-aware datetime or None if parsing fails
    """
    import zoneinfo
    
    if not datetime_str:
        return None
    
    try:
        dt = datetime.strptime(datetime_str.strip(), datetime_format)
        
        # Localize to timezone
        try:
            tz = zoneinfo.ZoneInfo(timezone_str)
            dt = dt.replace(tzinfo=tz)
        except Exception:
            # Fallback to naive datetime
            pass
        
        return dt
    except ValueError as e:
        raise ValueError(f"Failed to parse datetime '{datetime_str}' with format '{datetime_format}': {e}")


def check_valid_time_window(valid_from: Optional[datetime], valid_until: Optional[datetime]) -> bool:
    """
    Check if a time window is valid (from <= until).
    
    Args:
        valid_from: Start of window
        valid_until: End of window
        
    Returns:
        True if window is valid or either value is None, False otherwise
    """
    if valid_from is None or valid_until is None:
        return True
    
    return valid_from <= valid_until


def split_name(full_name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Split a full name into first and last name.
    
    Assumes format "FirstName LastName" or "LastName, FirstName"
    
    Args:
        full_name: Full name string
        
    Returns:
        Tuple of (first_name, last_name)
    """
    if not full_name:
        return None, None
    
    full_name = full_name.strip()
    
    # Try "LastName, FirstName" format first (comma present)
    if ',' in full_name:
        parts = full_name.split(',', 1)
        if len(parts) == 2:
            return parts[1].strip(), parts[0].strip()
    
    # Try "FirstName LastName" format
    parts = full_name.split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    
    # Single name
    return None, full_name
