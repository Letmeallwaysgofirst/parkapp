"""SQLAlchemy database models."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Text, Boolean, Integer, DateTime, ForeignKey, Enum, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ProviderType(str, enum.Enum):
    """Parking provider types."""
    KRAVAG = "KRAVAG"
    TRUCKS_NB = "TRUCKS_NB"
    SNAP = "SNAP"
    HOMEPAGE = "HOMEPAGE"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class ReservationStatus(str, enum.Enum):
    """Reservation status."""
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    DONE = "DONE"


class QueueReason(str, enum.Enum):
    """Clarification queue reason types."""
    UNKNOWN_PROVIDER = "UNKNOWN_PROVIDER"
    PARSE_FAILED = "PARSE_FAILED"
    SUSPECTED_DUPLICATE = "SUSPECTED_DUPLICATE"
    CANCEL_OR_CHANGE_MAIL = "CANCEL_OR_CHANGE_MAIL"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"


class SpotType(str, enum.Enum):
    """Parking spot types."""
    TRUCK = "TRUCK"
    CAR = "CAR"
    WOMEN = "WOMEN"


class ParkingSpot(Base):
    """Parking spot model."""
    __tablename__ = "parking_spots"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spot_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    row_label: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    spot_type: Mapped[str] = mapped_column(String(10), nullable=False, default=SpotType.TRUCK.value)
    
    # Geometry (percentage coordinates 0-100)
    x: Mapped[float] = mapped_column(Integer, nullable=False)
    y: Mapped[float] = mapped_column(Integer, nullable=False)
    width: Mapped[float] = mapped_column(Integer, nullable=False)
    height: Mapped[float] = mapped_column(Integer, nullable=False)
    rotation: Mapped[float] = mapped_column(Integer, nullable=False, default=0)
    
    # Status
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    # Relationships
    reservations: Mapped[list["Reservation"]] = relationship(
        "Reservation",
        back_populates="spot",
        foreign_keys="Reservation.spot_id"
    )
    
    def __repr__(self) -> str:
        return f"<ParkingSpot(id={self.id}, number={self.spot_number}, type={self.spot_type})>"


class Reservation(Base):
    """Parking reservation model."""
    __tablename__ = "reservations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Provider info
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    
    # External reference
    external_reservation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Personal info
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Vehicle
    plate_raw: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    plate_normalized: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    
    # Time window
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    
    # Booking timestamp (when the reservation was made)
    booked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Voucher
    voucher_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW")
    
    # Flags
    incomplete_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    duplicate_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    
    # Source tracking
    source_message_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, index=True)
    source_mail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Phase 2 reserved field
    pushed_to_designa_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Parking spot assignment
    spot_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("parking_spots.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    
    # Relationships
    mail_log_entries: Mapped[list["MailLog"]] = relationship(
        "MailLog", 
        back_populates="reservation",
        foreign_keys="MailLog.reservation_id"
    )
    spot: Mapped[Optional["ParkingSpot"]] = relationship(
        "ParkingSpot",
        back_populates="reservations",
        foreign_keys=[spot_id]
    )
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_reservation_status', 'status'),
        Index('idx_reservation_provider', 'provider'),
        Index('idx_reservation_window', 'valid_from', 'valid_until'),
        Index('idx_reservation_created', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Reservation(id={self.id}, provider={self.provider}, plate={self.plate_raw}, status={self.status})>"


class MailLog(Base):
    """Mail processing log."""
    __tablename__ = "mail_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_detected: Mapped[str] = mapped_column(String(50), nullable=False)
    parse_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Duplicate tracking
    duplicate_of: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("mail_log.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Reservation link
    reservation_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("reservations.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Raw mail path
    raw_mail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    
    # Relationships
    reservation: Mapped[Optional["Reservation"]] = relationship(
        "Reservation",
        back_populates="mail_log_entries",
        foreign_keys=[reservation_id]
    )
    
    duplicate_of_entry: Mapped[Optional["MailLog"]] = relationship(
        "MailLog",
        remote_side=[id],
        foreign_keys=[duplicate_of]
    )
    
    def __repr__(self) -> str:
        return f"<MailLog(id={self.id}, message_id={self.message_id[:50]}..., provider={self.provider_detected})>"


class ParseQueue(Base):
    """Clarification queue for problematic emails."""
    __tablename__ = "parse_queue"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_mail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    resolved_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        Index('idx_queue_reason', 'reason'),
        Index('idx_queue_unresolved', 'resolved', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<ParseQueue(id={self.id}, message_id={self.message_id[:50]}..., reason={self.reason}, resolved={self.resolved})>"
