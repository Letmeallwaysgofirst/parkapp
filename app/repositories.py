"""Repository layer for database access."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from app.config import get_configured_timezone
from app.models import Reservation, MailLog, ParseQueue, ReservationStatus, QueueReason, ParkingSpot, SpotType
from app.parsers import ParsedReservation, normalize_license_plate

logger = logging.getLogger(__name__)


class ReservationRepository:
    """Repository for reservation operations."""
    
    def __init__(self, session: Session):
        self.session = session
        self.timezone = ZoneInfo(get_configured_timezone())
    
    def create(self, parsed: ParsedReservation) -> Reservation:
        """Create a new reservation from parsed data."""
        reservation = Reservation(
            provider=parsed.provider,
            external_reservation_id=parsed.external_reservation_id,
            first_name=parsed.first_name,
            last_name=parsed.last_name,
            email=parsed.email,
            plate_raw=parsed.plate_raw,
            plate_normalized=parsed.plate_normalized,
            valid_from=parsed.valid_from,
            valid_until=parsed.valid_until,
            booked_at=parsed.booked_at,
            voucher_code=parsed.voucher_code,
            status=ReservationStatus.NEW.value,
            incomplete_flag=parsed.incomplete_flag,
            duplicate_flag=False,
            source_message_id=parsed.source_message_id,
            source_mail_path=parsed.source_mail_path,
            notes=parsed.notes,
        )
        
        self.session.add(reservation)
        self.session.flush()
        return reservation
    
    def get_by_id(self, reservation_id: int) -> Optional[Reservation]:
        """Get reservation by ID."""
        return self.session.query(Reservation).filter(Reservation.id == reservation_id).first()
    
    def get_by_message_id(self, message_id: str) -> Optional[Reservation]:
        """Get reservation by source message ID."""
        return self.session.query(Reservation).filter(
            Reservation.source_message_id == message_id
        ).first()
    
    def find_current(self, grace_minutes: int = 0) -> List[Reservation]:
        """Find reservations currently active (valid_from <= now <= valid_until + grace)."""
        now = datetime.now(self.timezone)
        grace_delta = timedelta(minutes=grace_minutes)
        
        return self.session.query(Reservation).filter(
            and_(
                Reservation.status.in_([ReservationStatus.NEW.value, ReservationStatus.CONFIRMED.value]),
                Reservation.valid_from <= now,
                Reservation.valid_until >= now - grace_delta
            )
        ).order_by(Reservation.valid_until.asc()).all()
    
    def find_upcoming(self, days: int = 7) -> List[Reservation]:
        """Find reservations starting within the next N days."""
        now = datetime.now(self.timezone)
        future = now + timedelta(days=days)
        
        return self.session.query(Reservation).filter(
            and_(
                Reservation.status.in_([ReservationStatus.NEW.value, ReservationStatus.CONFIRMED.value]),
                Reservation.valid_from >= now,
                Reservation.valid_from <= future
            )
        ).order_by(Reservation.valid_from.asc()).all()
    
    def find_arriving_today(self) -> List[Reservation]:
        """Find reservations arriving today."""
        today_start = datetime.now(self.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        return self.session.query(Reservation).filter(
            and_(
                Reservation.status.in_([ReservationStatus.NEW.value, ReservationStatus.CONFIRMED.value]),
                Reservation.valid_from >= today_start,
                Reservation.valid_from < today_end
            )
        ).order_by(Reservation.valid_from.asc()).all()
    
    def find_all(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_until: Optional[datetime] = None,
        search_text: Optional[str] = None,
        page: int = 1,
        per_page: int = 25
    ) -> Tuple[List[Reservation], int]:
        """Find reservations with filters and pagination."""
        query = self.session.query(Reservation)
        
        filters = []
        
        if provider:
            filters.append(Reservation.provider == provider)
        
        if status:
            filters.append(Reservation.status == status)
        
        if date_from:
            filters.append(Reservation.valid_from >= date_from)
        
        if date_until:
            filters.append(Reservation.valid_until <= date_until)
        
        if search_text:
            # Tolerant search: match against normalized plate and name
            normalized = normalize_license_plate(search_text)
            if normalized:
                filters.append(
                    or_(
                        Reservation.plate_normalized.like(f'%{normalized}%'),
                        func.lower(Reservation.first_name).like(f'%{search_text.lower()}%'),
                        func.lower(Reservation.last_name).like(f'%{search_text.lower()}%')
                    )
                )
            else:
                filters.append(
                    or_(
                        func.lower(Reservation.first_name).like(f'%{search_text.lower()}%'),
                        func.lower(Reservation.last_name).like(f'%{search_text.lower()}%')
                    )
                )
        
        if filters:
            query = query.filter(and_(*filters))
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        reservations = query.order_by(Reservation.created_at.desc()).offset(offset).limit(per_page).all()
        
        return reservations, total
    
    def check_heuristic_duplicate(
        self, 
        plate_normalized: str, 
        provider: str, 
        valid_from: datetime,
        valid_until: datetime,
        exclude_id: Optional[int] = None
    ) -> Optional[Reservation]:
        """
        Check for heuristic duplicate (same plate + provider + overlapping window).
        
        Returns the existing reservation if found, None otherwise.
        """
        if not plate_normalized or not provider or not valid_from or not valid_until:
            return None
        
        query = self.session.query(Reservation).filter(
            and_(
                Reservation.plate_normalized == plate_normalized,
                Reservation.provider == provider,
                Reservation.status.in_([ReservationStatus.NEW.value, ReservationStatus.CONFIRMED.value]),
                # Check for overlap
                Reservation.valid_from <= valid_until,
                Reservation.valid_until >= valid_from
            )
        )
        
        if exclude_id:
            query = query.filter(Reservation.id != exclude_id)
        
        return query.first()
    
    def update(self, reservation: Reservation, **kwargs) -> Reservation:
        """Update reservation fields."""
        for key, value in kwargs.items():
            if hasattr(reservation, key):
                setattr(reservation, key, value)
        
        reservation.updated_at = datetime.now(self.timezone)
        self.session.flush()
        return reservation
    
    def update_status(self, reservation_id: int, status: str, note: Optional[str] = None) -> Optional[Reservation]:
        """Update reservation status with optional note."""
        reservation = self.get_by_id(reservation_id)
        if reservation:
            reservation.status = status
            reservation.updated_at = datetime.now(self.timezone)
            
            if note:
                existing_notes = reservation.notes or ""
                reservation.notes = f"{existing_notes}\n[{datetime.now(self.timezone).isoformat()}] {note}".strip()
        
        return reservation
    
    def delete(self, reservation_id: int) -> bool:
        """Delete a reservation."""
        reservation = self.get_by_id(reservation_id)
        if reservation:
            self.session.delete(reservation)
            self.session.flush()
            return True
        return False
    
    def assign_to_spot(self, reservation_id: int, spot_id: int, note: Optional[str] = None) -> Optional[Reservation]:
        """
        Assign a reservation to a spot. If the reservation already has a spot,
        that spot is released (move semantics). Returns the reservation.
        """
        reservation = self.get_by_id(reservation_id)
        if not reservation:
            return None
        
        # If reservation already has a spot, that spot will be freed (no action needed here)
        # The caller should handle releasing the old spot if needed
        reservation.spot_id = spot_id
        reservation.updated_at = datetime.now(self.timezone)
        
        if note:
            existing_notes = reservation.notes or ""
            reservation.notes = f"{existing_notes}\n[{datetime.now(self.timezone).isoformat()}] {note}".strip()
        
        self.session.flush()
        return reservation
    
    def release_from_spot(self, reservation_id: int) -> Optional[Reservation]:
        """Release a reservation from its spot (unassign, keep reservation)."""
        reservation = self.get_by_id(reservation_id)
        if reservation:
            reservation.spot_id = None
            reservation.updated_at = datetime.now(self.timezone)
            self.session.flush()
        return reservation
    
    def _active_reservations_query(self):
        """Return query for active reservations (NEW or CONFIRMED within valid window)."""
        now = datetime.now(self.timezone)
        return self.session.query(Reservation).filter(
            and_(
                Reservation.status.in_([ReservationStatus.NEW.value, ReservationStatus.CONFIRMED.value]),
                Reservation.valid_from <= now,
                Reservation.valid_until >= now
            )
        )
    
    def find_active_without_spot(self) -> List[Reservation]:
        """Find active reservations without a spot assignment."""
        return self._active_reservations_query().filter(
            Reservation.spot_id.is_(None)
        ).order_by(Reservation.valid_until.asc()).all()
    
    def find_active_with_spot(self) -> List[Reservation]:
        """Find active reservations with a spot assignment."""
        return self._active_reservations_query().filter(
            Reservation.spot_id.isnot(None)
        ).order_by(Reservation.valid_until.asc()).all()
    
    def find_active_on_spot(self, spot_id: int) -> Optional[Reservation]:
        """Find the active reservation on a specific spot (if any)."""
        return self._active_reservations_query().filter(
            Reservation.spot_id == spot_id
        ).first()


class MailLogRepository:
    """Repository for mail log operations."""
    
    def __init__(self, session: Session):
        self.session = session
        self.timezone = ZoneInfo(get_configured_timezone())
    
    def create(
        self,
        message_id: str,
        provider: str,
        parse_ok: bool,
        raw_mail_path: Optional[str] = None,
        reservation_id: Optional[int] = None,
        duplicate_of: Optional[int] = None
    ) -> MailLog:
        """Create a new mail log entry."""
        log = MailLog(
            message_id=message_id,
            received_at=datetime.now(self.timezone),
            provider_detected=provider,
            parse_ok=parse_ok,
            raw_mail_path=raw_mail_path,
            reservation_id=reservation_id,
            duplicate_of=duplicate_of
        )
        
        self.session.add(log)
        self.session.flush()
        return log
    
    def get_by_message_id(self, message_id: str) -> Optional[MailLog]:
        """Get mail log by message ID."""
        return self.session.query(MailLog).filter(MailLog.message_id == message_id).first()
    
    def is_duplicate_message(self, message_id: str) -> bool:
        """Check if message ID has been processed before."""
        return self.get_by_message_id(message_id) is not None


class ParseQueueRepository:
    """Repository for clarification queue operations."""
    
    def __init__(self, session: Session):
        self.session = session
        self.timezone = ZoneInfo(get_configured_timezone())
    
    def create(
        self,
        message_id: str,
        reason: str,
        raw_mail_path: Optional[str] = None,
        note: Optional[str] = None
    ) -> ParseQueue:
        """Create a new queue entry."""
        entry = ParseQueue(
            message_id=message_id,
            reason=reason,
            raw_mail_path=raw_mail_path,
            resolved=False,
            notes=note
        )
        
        self.session.add(entry)
        self.session.flush()
        return entry
    
    def get_unresolved(self) -> List[ParseQueue]:
        """Get all unresolved queue entries."""
        return self.session.query(ParseQueue).filter(
            ParseQueue.resolved == False
        ).order_by(ParseQueue.created_at.desc()).all()
    
    def get_unresolved_count(self) -> int:
        """Get count of unresolved queue entries."""
        return self.session.query(ParseQueue).filter(
            ParseQueue.resolved == False
        ).count()
    
    def resolve(
        self,
        queue_id: int,
        note: Optional[str] = None
    ) -> Optional[ParseQueue]:
        """Mark queue entry as resolved."""
        entry = self.session.query(ParseQueue).filter(ParseQueue.id == queue_id).first()
        if entry:
            entry.resolved = True
            entry.resolved_note = note
        return entry
    
    def get_by_message_id(self, message_id: str) -> List[ParseQueue]:
        """Get queue entries by message ID."""
        return self.session.query(ParseQueue).filter(
            ParseQueue.message_id == message_id
        ).all()


class ParkingSpotRepository:
    """Repository for parking spot operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_by_id(self, spot_id: int) -> Optional[ParkingSpot]:
        """Get spot by ID."""
        return self.session.query(ParkingSpot).filter(ParkingSpot.id == spot_id).first()
    
    def get_by_number(self, spot_number: str) -> Optional[ParkingSpot]:
        """Get spot by spot number."""
        return self.session.query(ParkingSpot).filter(
            ParkingSpot.spot_number == spot_number
        ).first()
    
    def get_all(self) -> List[ParkingSpot]:
        """Get all spots ordered by spot number."""
        return self.session.query(ParkingSpot).order_by(
            ParkingSpot.spot_number
        ).all()
    
    def get_by_type(self, spot_type: str) -> List[ParkingSpot]:
        """Get all spots of a given type."""
        return self.session.query(ParkingSpot).filter(
            ParkingSpot.spot_type == spot_type
        ).order_by(ParkingSpot.spot_number).all()
    
    def get_free_spots(self, spot_type: Optional[str] = None) -> List[ParkingSpot]:
        """Get all free (not occupied, not closed) spots."""
        query = self.session.query(ParkingSpot).filter(
            ParkingSpot.is_closed == False
        )
        if spot_type:
            query = query.filter(ParkingSpot.spot_type == spot_type)
        return query.order_by(ParkingSpot.spot_number).all()
    
    def close_spot(self, spot_id: int, reason: str) -> Optional[ParkingSpot]:
        """Close a spot with a reason."""
        spot = self.get_by_id(spot_id)
        if spot:
            spot.is_closed = True
            spot.closed_reason = reason
        return spot
    
    def open_spot(self, spot_id: int) -> Optional[ParkingSpot]:
        """Open/unsperren a spot."""
        spot = self.get_by_id(spot_id)
        if spot:
            spot.is_closed = False
            spot.closed_reason = None
        return spot
    
    def upsert_from_yaml(
        self,
        spot_number: str,
        row_label: Optional[str],
        spot_type: str,
        x: float,
        y: float,
        width: float,
        height: float,
        rotation: float
    ) -> ParkingSpot:
        """
        Create or update a spot from YAML data.
        Preserves is_closed and closed_reason if spot exists.
        """
        spot = self.get_by_number(spot_number)
        if spot:
            # Update geometry only
            spot.row_label = row_label
            spot.spot_type = spot_type
            spot.x = x
            spot.y = y
            spot.width = width
            spot.height = height
            spot.rotation = rotation
        else:
            spot = ParkingSpot(
                spot_number=spot_number,
                row_label=row_label,
                spot_type=spot_type,
                x=x,
                y=y,
                width=width,
                height=height,
                rotation=rotation,
                is_closed=False,
                closed_reason=None
            )
            self.session.add(spot)
        self.session.flush()
        return spot
    
    def count(self) -> int:
        """Count total spots."""
        return self.session.query(ParkingSpot).count()
    
    def count_by_status(self) -> dict:
        """Count spots by status (free, occupied, closed)."""
        from sqlalchemy import func
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.config import get_configured_timezone
        
        tz = ZoneInfo(get_configured_timezone())
        now = datetime.now(tz)
        
        # Get all spots
        all_spots = self.get_all()
        total = len(all_spots)
        closed = sum(1 for s in all_spots if s.is_closed)
        
        # Count occupied spots (have an active reservation with spot_id set)
        # Active = status in (NEW, CONFIRMED) and valid_from <= now <= valid_until
        from app.models import Reservation, ReservationStatus
        occupied_ids = set()
        active_reservations = self.session.query(Reservation).filter(
            Reservation.status.in_([ReservationStatus.NEW.value, ReservationStatus.CONFIRMED.value]),
            Reservation.valid_from <= now,
            Reservation.valid_until >= now,
            Reservation.spot_id.isnot(None)
        ).all()
        for res in active_reservations:
            if res.spot_id:
                occupied_ids.add(res.spot_id)
        
        occupied = len(occupied_ids)
        free = total - occupied - closed
        
        return {
            "total": total,
            "free": free,
            "occupied": occupied,
            "closed": closed
        }
