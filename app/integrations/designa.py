"""
Designa SOAP Integration Stub - Phase 2

This module provides the interface for pushing reservations to the Designa parking system
via the `insertPrebookingData` SOAP operation.

IMPORTANT: The Designa SOAP endpoint is only reachable from the operator's internal network.
Phase 2 must run on-premise where network access to the Designa server is available.

Usage (Phase 2 implementation):
    result = push_reservation(reservation)
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime

# Not implemented in v1 - will be implemented in Phase 2
# Keeping this import for documentation purposes
# from app.models import Reservation


@dataclass
class PushResult:
    """Result of pushing a reservation to Designa."""
    success: bool
    designa_reservation_id: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[str] = None


#: Mapping table: Reservation fields -> Designa SOAP parameters for insertPrebookingData
#: 
#: Reservation field        -> Designa parameter             -> Description
#: -----------------------  -> -----------------------------  -> ------------------------------------------
#: provider                 -> TransactionType               -> Type of transaction (e.g., "WEB", "MANUAL")
#: id (internal)            -> ReservationID                 -> Internal reservation ID
#: plate_raw                -> VehicleRegistrationNumber    -> Vehicle license plate
#: -                        -> IdentMedium                  -> Identification medium (e.g., "PLATE")
#: valid_from               -> ValidFrom                    -> Start of reservation window
#: valid_until              -> ValidUntil                   -> End of reservation window
#: -                        -> GraceEntry                    -> Grace period for entry (minutes)
#: -                        -> LatestEntryOffset             -> Latest entry offset (minutes)
#: -                        -> ForcedCloseOffset            -> Forced close offset (minutes)
#: -                        -> TicketHandlingType            -> How tickets are handled
#: -                        -> PaymentType                  -> Payment method
#: -                        -> PaymentValue                  -> Payment amount
#: -                        -> BookingTariffId               -> Tariff for booking period
#: -                        -> OverstayTariffId              -> Tariff for overstay
#: last_name                -> LastName                      -> Customer last name
#: first_name               -> FirstName                     -> Customer first name
#: email                    -> Data1                         -> Custom data field 1
#: voucher_code             -> Data2                         -> Custom data field 2
#: -                        -> Data3                         -> Custom data field 3
#: -                        -> Data4                         -> Custom data field 4
#: -
#: NOTE: user/pwd parameters are for SOAP authentication, not stored in reservation
#:
#: Example SOAP request structure:
#: <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
#:   <soap:Header>
#:     <AuthenticationHeader>
#:       <user>DESIGNA_USER</user>
#:       <pwd>DESIGNA_PASSWORD</pwd>
#:     </AuthenticationHeader>
#:   </soap:Header>
#:   <soap:Body>
#:     <insertPrebookingData>
#:       <ReservationID>RES123</ReservationID>
#:       <TransactionType>WEB</TransactionType>
#:       <CarparkCode>PLOT01</CarparkCode>
#:       <VehicleRegistrationNumber>ABC123</VehicleRegistrationNumber>
#:       <IdentMedium>PLATE</IdentMedium>
#:       <ValidFrom>2026-05-11T21:45:00+02:00</ValidFrom>
#:       <ValidUntil>2026-05-12T08:00:00+02:00</ValidUntil>
#:       <LastName>Mustermann</LastName>
#:       <FirstName>Max</FirstName>
#:     </insertPrebookingData>
#:   </soap:Body>
#: </soap:Envelope>


class DesignaIntegrationError(Exception):
    """Raised when Designa integration encounters an error."""
    pass


def push_reservation(reservation) -> PushResult:
    """
    Push a reservation to the Designa parking system.
    
    This is a STUB that raises NotImplementedError.
    
    Phase 2 implementation will:
    1. Read Designa credentials from config (not .env for security)
    2. Build the SOAP request with insertPrebookingData operation
    3. Send to the Designa SOAP endpoint
    4. Parse the response and return PushResult
    
    Args:
        reservation: Reservation model instance to push
        
    Returns:
        PushResult with success status and Designa reservation ID
        
    Raises:
        NotImplementedError: This function is not implemented in v1
    """
    raise NotImplementedError(
        "Designa integration is not implemented in v1. "
        "This is a Phase 2 feature. See designa.py for the parameter mapping table."
    )


def get_designa_field_mapping() -> dict:
    """
    Return the field mapping table for documentation purposes.
    
    Returns:
        Dictionary mapping reservation fields to Designa SOAP parameters
    """
    return {
        'provider': 'TransactionType',
        'external_reservation_id': 'ReservationID',
        'plate_raw': 'VehicleRegistrationNumber',
        'valid_from': 'ValidFrom',
        'valid_until': 'ValidUntil',
        'last_name': 'LastName',
        'first_name': 'FirstName',
        'email': 'Data1',
        'voucher_code': 'Data2',
    }
