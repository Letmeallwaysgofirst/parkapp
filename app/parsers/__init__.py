"""Parser package for extracting reservation data from emails."""

from app.parsers.registry import ParserRegistry, parse_email_message, ParsedReservation, ParseResult
from app.parsers.normalizer import (
    normalize_license_plate,
    parse_datetime_explicit,
    parse_datetime_combined,
    split_name,
    check_valid_time_window
)

__all__ = [
    'ParserRegistry',
    'parse_email_message',
    'ParsedReservation',
    'ParseResult',
    'normalize_license_plate',
    'parse_datetime_explicit',
    'parse_datetime_combined',
    'split_name',
    'check_valid_time_window',
]
