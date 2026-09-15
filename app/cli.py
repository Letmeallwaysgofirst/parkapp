"""CLI commands for Parking Cockpit."""

import sys
import logging
import asyncio
from pathlib import Path
from typing import Optional
import click

from app.config import get_settings, get_base_dir
from app.db import init_db, get_db_session
from app.mail_poller import create_poller_from_config, MailPoller
from app.parsers import ParserRegistry, parse_email_message, ParsedReservation
from app.repositories import ReservationRepository, MailLogRepository
from app.parsers.normalizer import normalize_license_plate


def setup_logging(level: str = "INFO") -> None:
    """Setup basic logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


@click.group()
def cli():
    """Parking Cockpit - Local parking reservation oversight."""
    pass


@cli.command()
@click.option('--host', default=None, help='Host to bind to')
@click.option('--port', default=None, type=int, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
def serve(host: Optional[str], port: Optional[int], reload: bool):
    """Start the web server and mail poller."""
    import uvicorn
    from app.web.routes import app
    from app.mail_poller import MailPoller
    
    settings, _, _, _, _ = get_settings()
    
    # Initialize database
    init_db()
    
    # Create and start mail poller
    poller = create_poller_from_config()
    if poller:
        poller.start()
        # Store poller reference in app state
        app.state.poller = poller
    
    # Get host/port from args or config
    bind_host = host or settings.app.host
    bind_port = port or settings.app.port
    
    print(f"Starting Parking Cockpit on {bind_host}:{bind_port}")
    print(f"Database: {settings.storage.database}")
    print(f"Mail polling: {'enabled' if poller else 'disabled'}")
    
    try:
        uvicorn.run(
            "app.web.routes:app",
            host=bind_host,
            port=bind_port,
            reload=reload,
            log_level="info"
        )
    finally:
        if poller:
            poller.stop()


@cli.command()
def poll_once():
    """Poll IMAP mailbox once (for testing or manual trigger)."""
    setup_logging()
    
    print("Polling IMAP mailbox once...")
    
    poller = create_poller_from_config()
    if not poller:
        print("Error: IMAP not configured or polling disabled")
        sys.exit(1)
    
    init_db()
    results = poller.poll_once()
    
    print(f"\nResults:")
    print(f"  Processed: {results['processed']}")
    print(f"  Success: {results['success']}")
    print(f"  Queued: {results['queued']}")
    print(f"  Duplicates: {results['duplicates']}")
    if results['errors']:
        print(f"  Errors: {len(results['errors'])}")
        for err in results['errors']:
            print(f"    - {err}")


@cli.command()
@click.argument('files', nargs=-1, type=click.Path(exists=True))
@click.option('--provider', default=None, help='Force provider assignment')
@click.option('--create/--no-create', default=True, help='Create reservations (default: create)')
def ingest(files, provider: Optional[str], create: bool):
    """Ingest local .eml files (for testing and development)."""
    setup_logging()
    
    if not files:
        print("Error: No files specified")
        sys.exit(1)
    
    init_db()
    
    registry = ParserRegistry()
    
    processed = 0
    success = 0
    queued = 0
    
    for filepath in files:
        filepath = Path(filepath)
        print(f"\nProcessing: {filepath}")
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Parse email
            subject, sender, sender_domain, body = parse_email_message(content)
            
            # Get message ID from headers
            import re
            msg_id_match = re.search(r'^Message-ID:\s*(.+)$', content, re.MULTILINE)
            message_id = msg_id_match.group(1).strip() if msg_id_match else filepath.stem
            
            print(f"  Subject: {subject[:60]}...")
            print(f"  From: {sender}")
            
            # Parse
            if provider:
                # Force provider
                from app.parsers import ParsedReservation
                parsed = ParsedReservation(provider=provider)
                parsed.source_message_id = message_id
                parsed.source_mail_path = str(filepath)
                parse_success = True
            else:
                result = registry.parse(body, subject, sender, sender_domain)
                parse_success = result.success
                parsed = result.reservation
                
                if parsed:
                    parsed.source_message_id = message_id
                    parsed.source_mail_path = str(filepath)
            
            print(f"  Provider: {parsed.provider if parsed else 'UNKNOWN'}")
            
            with get_db_session() as session:
                mail_log_repo = MailLogRepository(session)
                reservation_repo = ReservationRepository(session)
                
                # Check for duplicate message
                if mail_log_repo.is_duplicate_message(message_id):
                    print(f"  Skipping: Duplicate message")
                    continue
                
                if parse_success and parsed and create:
                    reservation = reservation_repo.create(parsed)
                    mail_log_repo.create(
                        message_id=message_id,
                        provider=parsed.provider,
                        parse_ok=True,
                        raw_mail_path=str(filepath),
                        reservation_id=reservation.id
                    )
                    print(f"  Created reservation #{reservation.id}")
                    success += 1
                else:
                    reason = 'PARSE_FAILED' if not parse_success else 'INCOMPLETE_DATA'
                    mail_log_repo.create(
                        message_id=message_id,
                        provider=parsed.provider if parsed else 'UNKNOWN',
                        parse_ok=False,
                        raw_mail_path=str(filepath)
                    )
                    print(f"  Queued: {reason}")
                    queued += 1
                
                session.commit()
            
            processed += 1
            
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*50}")
    print(f"Processed: {processed}")
    print(f"  Success: {success}")
    print(f"  Queued: {queued}")


@cli.command()
def initdb():
    """Initialize the database."""
    setup_logging()
    init_db()
    seed_spots_from_yaml()
    print("Database initialized successfully")


@cli.command()
def spots_reload():
    """Reload spots from spots.yaml (preserves closures and assignments)."""
    setup_logging()
    init_db()
    count = seed_spots_from_yaml()
    print(f"Spots reloaded: {count} spots processed")


def seed_spots_from_yaml() -> int:
    """Load/update spots from spots.yaml. Returns count of spots processed."""
    import yaml
    
    base_dir = get_base_dir()
    spots_yaml_path = base_dir / "spots.yaml"
    
    if not spots_yaml_path.exists():
        print(f"Warning: {spots_yaml_path} not found, skipping spot seeding")
        return 0
    
    with open(spots_yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    spots_data = data.get("spots", []) if data else []
    
    count = 0
    with get_db_session() as session:
        from app.repositories import ParkingSpotRepository
        spot_repo = ParkingSpotRepository(session)
        
        for spot_data in spots_data:
            spot_repo.upsert_from_yaml(
                spot_number=spot_data["spot_number"],
                row_label=spot_data.get("row_label"),
                spot_type=spot_data.get("spot_type", "TRUCK"),
                x=spot_data["x"],
                y=spot_data["y"],
                width=spot_data["width"],
                height=spot_data["height"],
                rotation=spot_data.get("rotation", 0)
            )
            count += 1
        
        session.commit()
    
    return count


@cli.command()
def status():
    """Show application status."""
    settings, imap_settings, _, _, _ = get_settings()
    
    print("Parking Cockpit Status")
    print("=" * 50)
    
    # Check database
    db_path = get_base_dir() / settings.storage.database
    print(f"Database: {db_path}")
    print(f"  Exists: {db_path.exists()}")
    
    # Check IMAP
    print(f"\nIMAP Configuration:")
    print(f"  Host: {imap_settings.host or '(not configured)'}")
    print(f"  Port: {imap_settings.port}")
    print(f"  User: {imap_settings.user or '(not configured)'}")
    print(f"  Configured: {'yes' if imap_settings.host else 'no'}")
    
    # Check polling
    print(f"\nPolling:")
    print(f"  Enabled: {settings.polling.enabled}")
    if settings.polling.enabled:
        print(f"  Interval: {settings.polling.interval_minutes} minutes")
    
    # Count records
    try:
        init_db()
        with get_db_session() as session:
            from app.models import Reservation, MailLog, ParseQueue
            
            res_count = session.query(Reservation).count()
            log_count = session.query(MailLog).count()
            queue_count = session.query(ParseQueue).filter(ParseQueue.resolved == False).count()
            
            print(f"\nRecords:")
            print(f"  Reservations: {res_count}")
            print(f"  Mail log entries: {log_count}")
            print(f"  Unresolved queue items: {queue_count}")
    except Exception as e:
        print(f"\nError reading database: {e}")


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
