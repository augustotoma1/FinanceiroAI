"""
FastAPI Application Entry Point

This module initializes the FastAPI application for the Financial Automation System.
It configures CORS, includes API routers, provides health check endpoint for monitoring,
and manages background job scheduling with APScheduler.

The application serves as the integration hub for:
- Claude AI conversational data collection
- Conta Azul accounting platform synchronization
- Autentique electronic signature workflow
- Delinquency analysis and monitoring

Background jobs run automatically on schedule:
- Client synchronization: every hour
- Financial data synchronization: daily at 2 AM
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.background import sync_clients_job, sync_financial_job

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize APScheduler
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.

    Startup:
        - Starts APScheduler
        - Schedules background jobs for Conta Azul synchronization

    Shutdown:
        - Gracefully stops APScheduler
    """
    # Startup: Initialize and start scheduler
    logger.info("Starting application and background job scheduler...")

    try:
        # Schedule client synchronization job - runs every hour
        scheduler.add_job(
            func=sync_clients_job,
            trigger=IntervalTrigger(hours=1),
            id='sync_clients',
            name='Sync clients from Conta Azul',
            replace_existing=True,
            max_instances=1  # Prevent concurrent executions
        )
        logger.info("Scheduled client synchronization job (every hour)")

        # Schedule financial data synchronization job - runs daily at 2 AM
        scheduler.add_job(
            func=sync_financial_job,
            trigger=CronTrigger(hour=2, minute=0),  # 2:00 AM daily
            id='sync_financial',
            name='Sync financial data from Conta Azul',
            replace_existing=True,
            max_instances=1  # Prevent concurrent executions
        )
        logger.info("Scheduled financial data synchronization job (daily at 2:00 AM)")

        # Start the scheduler
        scheduler.start()
        logger.info("Background job scheduler started successfully")

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        raise

    yield  # Application runs here

    # Shutdown: Stop scheduler gracefully
    logger.info("Shutting down background job scheduler...")
    try:
        scheduler.shutdown(wait=True)  # Wait for running jobs to complete
        logger.info("Background job scheduler stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}", exc_info=True)

# Initialize FastAPI application with metadata and lifespan management
app = FastAPI(
    title="Financial Automation System",
    description="AI-powered financial automation with Conta Azul and Autentique integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan  # Manage scheduler startup/shutdown
)

# Configure CORS middleware for browser-based dashboard access
# Allows requests from specified origins with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancer probes.

    Returns a simple status indicating the application is running.
    Can be extended to include database connectivity checks and
    external service availability status.

    Returns:
        dict: Status object with "status" field set to "healthy"
    """
    return {"status": "healthy"}


@app.get("/")
async def root():
    """
    Root endpoint providing basic API information.

    Returns:
        dict: Welcome message and API documentation links
    """
    return {
        "message": "Financial Automation System API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# API router includes
from app.api import conversation, clients, contracts, signatures, auth, dashboard

# Include routers with prefixes and tags
app.include_router(conversation.router, prefix="/api/conversation", tags=["conversation"])
app.include_router(clients.router, prefix="/api/clients", tags=["clients"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
app.include_router(signatures.router, prefix="/api/signatures", tags=["signatures"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
