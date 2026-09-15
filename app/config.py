"""Configuration loading from .env and YAML files."""

import os
import logging
from pathlib import Path
from typing import Optional
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class AppConfig(BaseModel):
    """Application server config."""
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    file: str = "parking_cockpit.log"
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


class PollingConfig(BaseModel):
    """Polling configuration."""
    interval_minutes: int = 5
    enabled: bool = True


class StorageConfig(BaseModel):
    """Storage paths configuration."""
    database: str = "parking_cockpit.db"
    raw_mails_folder: str = "raw_mails"
    retention_days: int = 365
    raw_mails_permissions: str = "0700"


class UIConfig(BaseModel):
    """UI display configuration."""
    upcoming_days: int = 7
    current_window_grace_minutes: int = 0
    auto_refresh_seconds: int = 60
    items_per_page: int = 25
    map_background: str = "schema"  # "schema" or "foto"


class AssignmentConfig(BaseModel):
    """Auto-assignment configuration."""
    auto_assign: bool = False


class MailboxConfig(BaseModel):
    """IMAP mailbox configuration."""
    seen_flags: list[str] = Field(default_factory=lambda: ["\\Seen"])
    archive_processed: bool = True


class ImapSettings(BaseSettings):
    """IMAP settings from environment variables."""
    host: str = Field(default="", alias="IMAP_HOST")
    port: int = Field(default=993, alias="IMAP_PORT")
    user: str = Field(default="", alias="IMAP_USER")
    password: str = Field(default="", alias="IMAP_PASS")
    
    class Config:
        extra = "ignore"


class SmtpSettings(BaseSettings):
    """SMTP settings from environment variables (optional)."""
    host: str = Field(default="", alias="SMTP_HOST")
    port: int = Field(default=587, alias="SMTP_PORT")
    user: str = Field(default="", alias="SMTP_USER")
    password: str = Field(default="", alias="SMTP_PASS")
    from_addr: str = Field(default="", alias="SMTP_FROM")
    to_addr: str = Field(default="", alias="SMTP_TO")
    
    class Config:
        extra = "ignore"


class UISettings(BaseSettings):
    """UI settings from environment variables."""
    password: str = Field(default="", alias="UI_PASSWORD")
    
    class Config:
        extra = "ignore"


class AppSettings(BaseModel):
    """Main application settings."""
    app: AppConfig = Field(default_factory=AppConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    timezone: str = "Europe/Berlin"
    polling: PollingConfig = Field(default_factory=PollingConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    assignment: AssignmentConfig = Field(default_factory=AssignmentConfig)
    mailbox: MailboxConfig = Field(default_factory=MailboxConfig)


def load_yaml_config(config_path: Optional[Path] = None) -> dict:
    """Load YAML configuration file."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        return {}
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_providers_config(providers_path: Optional[Path] = None) -> dict:
    """Load providers configuration file."""
    if providers_path is None:
        providers_path = Path(__file__).parent.parent / "providers.yaml"
    
    if not providers_path.exists():
        logger.warning(f"Providers config not found: {providers_path}")
        return {}
    
    with open(providers_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache()
def get_settings() -> tuple[AppSettings, ImapSettings, SmtpSettings, UISettings, dict]:
    """Get all settings - cached for performance."""
    # Load YAML config
    yaml_config = load_yaml_config()
    
    # Create app settings
    app_settings = AppSettings(**yaml_config)
    
    # Load environment settings
    imap_settings = ImapSettings()
    smtp_settings = SmtpSettings()
    ui_settings = UISettings()
    
    # Load providers config
    providers_config = load_providers_config()
    
    return app_settings, imap_settings, smtp_settings, ui_settings, providers_config


def get_configured_timezone() -> str:
    """Get configured timezone string."""
    settings, *_ = get_settings()
    return settings.timezone


def get_base_dir() -> Path:
    """Get the base directory (project root)."""
    return Path(__file__).parent.parent


def get_database_path() -> Path:
    """Get the database file path."""
    settings, *_ = get_settings()
    base_dir = get_base_dir()
    db_path = base_dir / settings.storage.database
    
    # Make path absolute if relative
    if not db_path.is_absolute():
        db_path = base_dir / db_path
    
    return db_path


def get_raw_mails_path() -> Path:
    """Get the raw mails folder path."""
    settings, *_ = get_settings()
    base_dir = get_base_dir()
    raw_mails_path = base_dir / settings.storage.raw_mails_folder
    
    # Make path absolute if relative
    if not raw_mails_path.is_absolute():
        raw_mails_path = base_dir / raw_mails_path
    
    return raw_mails_path
