# Parking Cockpit

A local-only web application for parking reservation oversight. Monitors IMAP mailbox for reservation emails from various parking portals, parses them, and provides a German-language dashboard for operators.

## Features

- **Automatic Email Polling**: Polls configured IMAP mailbox at configurable intervals
- **Multi-Provider Support**: Detects and parses emails from Kravag, Trucks nB, SNAP, and homepage reservations
- **Local-Only**: No cloud services, no external APIs, 100% local data storage
- **German Web Dashboard**: View current, upcoming, and historical reservations
- **Clarification Queue**: Handle problematic emails that need manual review
- **CSV Export**: Export filtered reservation data
- **Privacy-First**: All personal data stays local in SQLite database

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example configuration files:

```bash
cp .env.example .env
cp config.yaml.example config.yaml
```

Edit `.env` with your settings:
```bash
IMAP_HOST=imap.your-provider.com
IMAP_PORT=993
IMAP_USER=parking@example.com
IMAP_PASS=your_password
UI_PASSWORD=your_secure_password
```

### 3. Initialize Database

```bash
python -m parking_cockpit initdb
```

### 4. Run the Application

```bash
python -m parking_cockpit serve
```

The web dashboard will be available at `http://127.0.0.1:8000`

### 5. Load Sample Data (for testing)

```bash
python -m parking_cockpit ingest samples/*.eml
```

## Command Line Interface

```bash
# Start web server and mail poller
python -m parking_cockpit serve

# Poll mailbox once
python -m parking_cockpit poll-once

# Ingest local .eml files (for testing)
python -m parking_cockpit ingest samples/*.eml

# Initialize database
python -m parking_cockpit initdb

# Show status
python -m parking_cockpit status
```

## Configuration Reference

### .env (Secrets)

| Variable | Description | Required |
|----------|-------------|----------|
| `IMAP_HOST` | IMAP server hostname | Yes |
| `IMAP_PORT` | IMAP server port (default: 993) | No |
| `IMAP_USER` | IMAP username | Yes |
| `IMAP_PASS` | IMAP password | Yes |
| `UI_PASSWORD` | Web dashboard password | Yes |

### config.yaml (Behavior)

```yaml
app:
  host: "127.0.0.1"    # Web server binding
  port: 8000           # Web server port

polling:
  interval_minutes: 5  # IMAP poll interval
  enabled: true

ui:
  upcoming_days: 7     # Days to show in "Kommend"
  current_window_grace_minutes: 0  # Grace period for current view
  auto_refresh_seconds: 60  # Auto-refresh interval (0 to disable)

storage:
  database: "parking_cockpit.db"
  raw_mails_folder: "raw_mails"
  retention_days: 365  # Days to keep raw emails

logging:
  level: "INFO"
```

### providers.yaml (Parser Configuration)

Each provider requires:
- **detection**: Rules to identify the provider (sender, subject, body markers)
- **extraction**: Field mappings to extract data from email
- **datetime**: Date/time format declarations

## Adding a New Portal Parser

To add support for a new parking portal:

1. **Add provider detection rules** to `providers.yaml`:
```yaml
providers:
  NEW_PORTAL:
    name: "New Portal Name"
    detection:
      rules:
        - type: "sender_domain"
          pattern: "newportal\\.com"
        - type: "subject"
          pattern: "Reservation.*Confirmed"
```

2. **Configure extraction rules**:
```yaml
    extraction:
      field_mappings:
        - target: "plate_raw"
          source_type: "value_after_marker"
          marker: "License Plate:"
```

3. **Define datetime formats** (explicit, never guess):
```yaml
    datetime:
      valid_from:
        date_source: "Start Date"
        date_format: "%Y-%m-%d"
        time_source: "Start Time"
        time_format: "%H:%M"
```

4. **Restart the application**

No code changes required for new parsers!

## Database Schema

### reservations
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| provider | VARCHAR | KRAVAG, TRUCKS_NB, SNAP, HOMEPAGE, MANUAL, UNKNOWN |
| plate_raw | VARCHAR | Original license plate |
| plate_normalized | VARCHAR | Normalized plate for search |
| first_name, last_name | VARCHAR | Customer name |
| email | VARCHAR | Customer email |
| valid_from, valid_until | DATETIME | Reservation window |
| status | VARCHAR | NEW, CONFIRMED, CANCELLED, DONE |
| incomplete_flag | BOOLEAN | Data is incomplete |
| duplicate_flag | BOOLEAN | Potential duplicate |
| notes | TEXT | Operator notes |

### mail_log
Tracks processed emails for audit trail.

### parse_queue
Clarification queue for emails requiring manual review.

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_parsers.py

# Run with coverage
pytest --cov=app tests/
```

## Phase 2: Designa Integration

Phase 2 will push reservations to Designa SOAP webservice.

**Important**: The Designa endpoint is only reachable from the operator's internal network. Phase 2 must run on-premise.

The interface is defined in `app/integrations/designa.py`:

```python
# Push reservation to Designa
result = push_reservation(reservation)
```

Field mapping table (reservation → Designa):
- `plate_raw` → `VehicleRegistrationNumber`
- `valid_from` → `ValidFrom`
- `valid_until` → `ValidUntil`
- `last_name` → `LastName`
- `first_name` → `FirstName`
- etc.

See `app/integrations/designa.py` for complete mapping documentation.

## Project Structure

```
parking_cockpit/
├── app/
│   ├── main.py           # FastAPI app entry point
│   ├── config.py         # Configuration loading
│   ├── db.py             # Database engine
│   ├── models.py         # SQLAlchemy models
│   ├── repositories.py   # Data access layer
│   ├── mail_poller.py    # IMAP polling service
│   ├── parsers/          # Email parsers
│   │   ├── registry.py   # Parser registry
│   │   └── normalizer.py # Data normalization
│   ├── integrations/    # External integrations
│   │   └── designa.py    # Phase 2 stub
│   ├── web/              # Web UI
│   │   ├── routes.py     # FastAPI routes
│   │   ├── templates/    # Jinja2 templates
│   │   └── static/       # CSS
│   └── cli.py            # CLI commands
├── samples/              # Test fixtures
├── tests/               # pytest tests
├── providers.yaml        # Provider configurations
├── config.yaml          # Application config
├── .env                 # Secrets
├── requirements.txt
└── README.md
```

## License

Local-only application for parking lot operators. All data stays on-premise.
