"""Mail polling service for fetching and processing reservation emails."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from imap_tools import MailBox, AND
try:
    from imap_tools.mailbox import MailBoxTls
except ImportError:
    try:
        from imap_tools import MailBoxTls
    except ImportError:
        from imap_tools import MailBox as MailBoxTls
try:
    from imap_tools.query import Query
except ImportError:
    try:
        from imap_tools import AND as Query
    except ImportError:
        Query = None

from app.config import (
    get_settings, 
    get_raw_mails_path, 
    get_configured_timezone,
    get_base_dir
)
from app.db import get_db_session
from app.models import ReservationStatus
from app.repositories import ReservationRepository, MailLogRepository, ParseQueueRepository
from app.parsers import ParserRegistry, parse_email_message, ParsedReservation

logger = logging.getLogger(__name__)


class MailPoller:
    """Polling service for IMAP mailbox."""
    
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        interval_minutes: int = 5,
        raw_mails_folder: Optional[Path] = None,
        seen_flags: Optional[list] = None,
        archive_processed: bool = True,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.interval_minutes = interval_minutes
        self.raw_mails_folder = raw_mails_path or get_raw_mails_path()
        self.seen_flags = seen_flags or ["\\Seen"]
        self.archive_processed = archive_processed
        self.timezone = ZoneInfo(get_configured_timezone())
        
        self._running = False
        self._parser_registry: Optional[ParserRegistry] = None
        self._task: Optional[asyncio.Task] = None
    
    @property
    def parser_registry(self) -> ParserRegistry:
        """Get or create parser registry."""
        if self._parser_registry is None:
            self._parser_registry = ParserRegistry()
        return self._parser_registry
    
    def _ensure_raw_mails_folder(self) -> None:
        """Ensure raw mails folder exists with proper permissions."""
        self.raw_mails_folder.mkdir(parents=True, exist_ok=True)
        # Set permissions to 0700 (owner only)
        try:
            os.chmod(self.raw_mails_folder, 0o700)
        except Exception as e:
            logger.warning(f"Could not set raw_mails_folder permissions: {e}")
    
    def _save_raw_mail(self, message_id: str, raw_content: bytes) -> Path:
        """Save raw email content to disk for audit trail."""
        self._ensure_raw_mails_folder()
        
        # Sanitize message ID for filename
        safe_id = "".join(c if c.isalnum() or c in '._-' else '_' for c in message_id[:100])
        filename = f"{safe_id}_{datetime.now(self.timezone).strftime('%Y%m%d_%H%M%S')}.eml"
        filepath = self.raw_mails_folder / filename
        
        with open(filepath, 'wb') as f:
            f.write(raw_content)
        
        return filepath
    
    def _mark_as_processed(self, mailbox: MailBoxTls, uid: str) -> None:
        """Mark message as processed in IMAP."""
        try:
            if self.seen_flags:
                for flag in self.seen_flags:
                    mailbox.flag(uid, flag, True)
        except Exception as e:
            logger.warning(f"Could not mark message {uid} as processed: {e}")
    
    def _process_single_message(
        self,
        msg,
        uid: str,
        mailbox: MailBoxTls
    ) -> Optional[tuple[str, str, str]]:
        """
        Process a single email message.
        
        Returns:
            Tuple of (message_id, provider, status) or None on skip
        """
        message_id = msg.uid or msg.headers.get('message-id', [f'unknown_{uid}'])[0]
        
        logger.info(f"Processing message: {message_id[:50]}...")
        
        # Parse the email
        subject, sender, sender_domain, body = parse_email_message(msg.text or msg.html or '')
        
        # Parse with registry
        parse_result = self.parser_registry.parse(body, subject, sender, sender_domain)
        
        # Save raw mail for audit
        raw_path = None
        try:
            # Get raw content - msg.original is only available during iteration
            raw_content = msg.original
            raw_path = self._save_raw_mail(message_id, raw_content)
        except Exception as e:
            logger.error(f"Failed to save raw mail: {e}")
        
        # Store parsed data
        parsed = parse_result.reservation
        if parsed:
            parsed.source_message_id = message_id
            parsed.source_mail_path = str(raw_path) if raw_path else None
        
        # Determine queue reason if parsing failed
        queue_reason = None
        if not parse_result.success:
            queue_reason = parse_result.queued_reason or 'PARSE_FAILED'
        
        return message_id, parse_result.provider, parse_result.success, raw_path, parsed, queue_reason, parse_result.error_message
    
    def poll_once(self) -> dict:
        """
        Perform a single poll of the IMAP mailbox.
        
        Returns:
            Dictionary with poll results summary
        """
        results = {
            'processed': 0,
            'success': 0,
            'queued': 0,
            'duplicates': 0,
            'errors': []
        }
        
        logger.info(f"Polling mailbox {self.username}@{self.host}:{self.port}")
        
        try:
            with MailBox(self.host, self.port).login(self.username, self.password) as mailbox:
                # Fetch unseen messages
                criteria = AND(seen=False)
                messages = list(mailbox.fetch(criteria))
                
                logger.info(f"Found {len(messages)} unseen messages")
                
                for msg in messages:
                    uid = msg.uid
                    try:
                        result = self._process_single_message(msg, uid, mailbox)
                        if result:
                            message_id, provider, success, raw_path, parsed, queue_reason, error_msg = result
                            
                            with get_db_session() as session:
                                mail_log_repo = MailLogRepository(session)
                                reservation_repo = ReservationRepository(session)
                                queue_repo = ParseQueueRepository(session)
                                
                                # Check for exact duplicate by message ID
                                if mail_log_repo.is_duplicate_message(message_id):
                                    logger.info(f"Skipping duplicate message: {message_id[:50]}")
                                    results['duplicates'] += 1
                                    continue
                                
                                # Create mail log entry
                                if success and parsed:
                                    # Check for heuristic duplicate
                                    if parsed.plate_normalized and parsed.valid_from and parsed.valid_until:
                                        existing = reservation_repo.check_heuristic_duplicate(
                                            parsed.plate_normalized,
                                            parsed.provider,
                                            parsed.valid_from,
                                            parsed.valid_until
                                        )
                                        if existing:
                                            logger.warning(
                                                f"Potential duplicate detected: plate={parsed.plate_raw}, "
                                                f"existing_id={existing.id}"
                                            )
                                            parsed.duplicate_flag = True
                                            parsed.notes = f"Potentieller Duplikat zu Reservierung #{existing.id}"
                                            queue_reason = 'SUSPECTED_DUPLICATE'
                                            success = False
                                    
                                    if parsed.incomplete_flag:
                                        queue_reason = 'INCOMPLETE_DATA'
                                        success = False
                                
                                # Create reservation if successful
                                reservation_id = None
                                if success and parsed:
                                    reservation = reservation_repo.create(parsed)
                                    reservation_id = reservation.id
                                    results['success'] += 1
                                else:
                                    results['queued'] += 1
                                    
                                    # Add to clarification queue
                                    queue_repo.create(
                                        message_id=message_id,
                                        reason=queue_reason or 'PARSE_FAILED',
                                        raw_mail_path=str(raw_path) if raw_path else None,
                                        note=error_msg
                                    )
                                
                                # Create mail log entry
                                mail_log_repo.create(
                                    message_id=message_id,
                                    provider=provider,
                                    parse_ok=success,
                                    raw_mail_path=str(raw_path) if raw_path else None,
                                    reservation_id=reservation_id
                                )
                                
                                session.commit()
                                
                                # Mark as processed
                                self._mark_as_processed(mailbox, uid)
                                
                                results['processed'] += 1
                                
                    except Exception as e:
                        logger.exception(f"Error processing message {uid}: {e}")
                        results['errors'].append(str(e))
                        
        except Exception as e:
            logger.exception(f"IMAP connection error: {e}")
            results['errors'].append(f"Connection error: {e}")
        
        logger.info(
            f"Poll complete: processed={results['processed']}, "
            f"success={results['success']}, queued={results['queued']}, "
            f"duplicates={results['duplicates']}, errors={len(results['errors'])}"
        )
        
        return results
    
    async def _poll_loop(self) -> None:
        """Background polling loop."""
        logger.info(f"Starting mail polling loop (interval={self.interval_minutes}m)")
        
        while self._running:
            try:
                # Run poll in executor to not block the event loop
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.poll_once)
            except Exception as e:
                logger.exception(f"Error in poll loop: {e}")
            
            # Sleep for interval
            await asyncio.sleep(self.interval_minutes * 60)
    
    def start(self) -> None:
        """Start the background polling task."""
        if self._running:
            logger.warning("Poller already running")
            return
        
        self._running = True
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._poll_loop())
        logger.info("Mail poller started")
    
    def stop(self) -> None:
        """Stop the background polling task."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Mail poller stopped")
    
    @property
    def is_running(self) -> bool:
        """Check if poller is running."""
        return self._running


def create_poller_from_config() -> Optional[MailPoller]:
    """Create a mail poller from application configuration."""
    settings, imap_settings, smtp_settings, ui_settings, providers_config = get_settings()
    
    if not imap_settings.host or not imap_settings.user or not imap_settings.password:
        logger.warning("IMAP not configured, poller disabled")
        return None
    
    if not settings.polling.enabled:
        logger.info("Polling disabled in config")
        return None
    
    raw_mails_path = get_base_dir() / settings.storage.raw_mails_folder
    
    return MailPoller(
        host=imap_settings.host,
        port=imap_settings.port,
        username=imap_settings.user,
        password=imap_settings.password,
        interval_minutes=settings.polling.interval_minutes,
        raw_mails_folder=raw_mails_path,
        seen_flags=settings.mailbox.seen_flags,
        archive_processed=settings.mailbox.archive_processed
    )
