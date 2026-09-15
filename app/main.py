"""
Parking Cockpit - Main entry point.

This module initializes the FastAPI application and starts the background
mail polling service.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings, get_base_dir, get_configured_timezone
from app.db import init_db
from app.mail_poller import create_poller_from_config, MailPoller

logger = logging.getLogger(__name__)


# Global poller reference
_poller: MailPoller = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _poller
    
    # Startup
    logger.info("Starting Parking Cockpit...")
    
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Create and start mail poller
    _poller = create_poller_from_config()
    if _poller:
        _poller.start()
        logger.info("Mail poller started")
        app.state.poller = _poller
    
    yield
    
    # Shutdown
    logger.info("Shutting down Parking Cockpit...")
    if _poller:
        _poller.stop()
        logger.info("Mail poller stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="Parking Cockpit",
        description="Local parking reservation oversight application",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Include web routes
    from app.web.routes import app as web_app
    app.mount("/", web_app)
    
    return app


# For direct execution
if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "app.main:create_app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
        factory=True
    )
