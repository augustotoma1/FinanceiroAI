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
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.background import (
    daily_ai_employee_job,
    daily_contract_lifecycle_job,
    daily_billing_email_job,
    daily_whatsapp_billing_job,
    sync_clients_job,
    sync_financial_job,
    sync_signatures_job,
)
from app.services.telegram_bot import (
    send_contract_lifecycle_alert,
    create_bot_application,
    send_ai_employee_alert,
    send_daily_cfo_alert,
    send_daily_email_billing_alert,
    send_weekly_cfo_alert,
    start_bot,
    stop_bot,
)
from app.services.cash_risk_service import persist_daily_cash_risk_snapshot
from app.api.dependencies import verify_api_key

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

    # Initialize Telegram bot (skip during tests to avoid 429 errors)
    is_testing = os.environ.get("TESTING") == "1"
    telegram_app = None if is_testing else create_bot_application()

    # In test mode, skip scheduler jobs entirely to avoid background side
    # effects (DB writes/races) that make API tests flaky.
    if is_testing:
        logger.info("TESTING=1 detected: skipping scheduler and Telegram startup")
        yield
        return

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

        if settings.AUTENTIQUE_SIGNATURE_SYNC_ENABLED:
            signature_interval = max(
                5, int(getattr(settings, "AUTENTIQUE_SIGNATURE_SYNC_INTERVAL_MINUTES", 30))
            )
            scheduler.add_job(
                func=sync_signatures_job,
                trigger=IntervalTrigger(minutes=signature_interval),
                id="sync_signatures",
                name="Sync Autentique signatures",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=1800,
            )
            logger.info(
                "Scheduled Autentique signature sync job (every %s minutes, max_contracts=%s, only_open=%s)",
                signature_interval,
                settings.AUTENTIQUE_SIGNATURE_SYNC_MAX_CONTRACTS,
                settings.AUTENTIQUE_SIGNATURE_SYNC_ONLY_OPEN,
            )

        # Schedule daily cash-risk snapshot persistence (5 minutes before CFO alert)
        snapshot_hour = settings.TELEGRAM_ALERT_HOUR
        snapshot_minute = settings.TELEGRAM_ALERT_MINUTE - 5
        if snapshot_minute < 0:
            snapshot_minute += 60
            snapshot_hour = (snapshot_hour - 1) % 24

        scheduler.add_job(
            func=persist_daily_cash_risk_snapshot,
            trigger=CronTrigger(hour=snapshot_hour, minute=snapshot_minute),
            id='daily_cash_risk_snapshot',
            name='Persist daily cash risk snapshot',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800,
        )
        logger.info(
            "Scheduled daily cash risk snapshot (%02d:%02d)",
            snapshot_hour,
            snapshot_minute,
        )

        if settings.CONTRACT_LIFECYCLE_ENABLED:
            scheduler.add_job(
                func=daily_contract_lifecycle_job,
                trigger=CronTrigger(
                    hour=settings.CONTRACT_LIFECYCLE_RUN_HOUR,
                    minute=settings.CONTRACT_LIFECYCLE_RUN_MINUTE,
                ),
                id="daily_contract_lifecycle",
                name="Contract lifecycle daily maintenance",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=1800,
            )
            logger.info(
                "Scheduled contract lifecycle maintenance (%02d:%02d) window=%sd",
                settings.CONTRACT_LIFECYCLE_RUN_HOUR,
                settings.CONTRACT_LIFECYCLE_RUN_MINUTE,
                settings.CONTRACT_LIFECYCLE_ALERT_DAYS,
            )

        if telegram_app:
            async def daily_cfo_alert_job():
                await send_daily_cfo_alert(telegram_app)

            scheduler.add_job(
                func=daily_cfo_alert_job,
                trigger=CronTrigger(
                    hour=settings.TELEGRAM_ALERT_HOUR,
                    minute=settings.TELEGRAM_ALERT_MINUTE,
                ),
                id='daily_cfo_alert',
                name='Send daily CFO alert on Telegram',
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=1800,
            )
            logger.info(
                "Scheduled daily CFO Telegram alert (%02d:%02d)",
                settings.TELEGRAM_ALERT_HOUR,
                settings.TELEGRAM_ALERT_MINUTE,
            )

            if settings.TELEGRAM_WEEKLY_ALERT_ENABLED:
                async def weekly_cfo_alert_job():
                    await send_weekly_cfo_alert(telegram_app)

                scheduler.add_job(
                    func=weekly_cfo_alert_job,
                    trigger=CronTrigger(
                        day_of_week=settings.TELEGRAM_WEEKLY_ALERT_DAY,
                        hour=settings.TELEGRAM_WEEKLY_ALERT_HOUR,
                        minute=settings.TELEGRAM_WEEKLY_ALERT_MINUTE,
                    ),
                    id='weekly_cfo_alert',
                    name='Send weekly CFO summary on Telegram',
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=1800,
                )
                logger.info(
                    "Scheduled weekly CFO Telegram summary (%s %02d:%02d)",
                    settings.TELEGRAM_WEEKLY_ALERT_DAY,
                    settings.TELEGRAM_WEEKLY_ALERT_HOUR,
                    settings.TELEGRAM_WEEKLY_ALERT_MINUTE,
                )

            if settings.CONTRACT_LIFECYCLE_ENABLED and settings.CONTRACT_LIFECYCLE_ALERT_ENABLED:
                async def daily_contract_lifecycle_alert_job():
                    await send_contract_lifecycle_alert(telegram_app)

                scheduler.add_job(
                    func=daily_contract_lifecycle_alert_job,
                    trigger=CronTrigger(
                        hour=settings.CONTRACT_LIFECYCLE_ALERT_HOUR,
                        minute=settings.CONTRACT_LIFECYCLE_ALERT_MINUTE,
                    ),
                    id="daily_contract_lifecycle_alert",
                    name="Send daily contract lifecycle alert on Telegram",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=1800,
                )
                logger.info(
                    "Scheduled contract lifecycle Telegram alert (%02d:%02d)",
                    settings.CONTRACT_LIFECYCLE_ALERT_HOUR,
                    settings.CONTRACT_LIFECYCLE_ALERT_MINUTE,
                )

        if settings.EMAIL_BILLING_ENABLED:
            billing_job_func = daily_billing_email_job
            billing_job_name = "Send daily billing reminder emails"
            if telegram_app:
                async def daily_billing_email_job_with_alert():
                    result = await daily_billing_email_job()
                    if bool(getattr(settings, "EMAIL_BILLING_ALERT_ENABLED", True)):
                        await send_daily_email_billing_alert(telegram_app, result)
                    return result

                billing_job_func = daily_billing_email_job_with_alert
                billing_job_name = "Send daily billing reminder emails + Telegram alert"

            scheduler.add_job(
                func=billing_job_func,
                trigger=CronTrigger(
                    hour=settings.EMAIL_BILLING_HOUR,
                    minute=settings.EMAIL_BILLING_MINUTE,
                ),
                id="daily_billing_email",
                name=billing_job_name,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=1800,
            )
            logger.info(
                "Scheduled billing email campaign (%02d:%02d) provider=%s dry_run=%s telegram_alert=%s",
                settings.EMAIL_BILLING_HOUR,
                settings.EMAIL_BILLING_MINUTE,
                settings.EMAIL_BILLING_PROVIDER,
                settings.EMAIL_BILLING_DRY_RUN,
                getattr(settings, "EMAIL_BILLING_ALERT_ENABLED", True),
            )

        if settings.WHATSAPP_FEATURE_ENABLED and settings.WHATSAPP_BILLING_ENABLED:
            scheduler.add_job(
                func=daily_whatsapp_billing_job,
                trigger=CronTrigger(
                    hour=settings.WHATSAPP_BILLING_HOUR,
                    minute=settings.WHATSAPP_BILLING_MINUTE,
                ),
                id="daily_whatsapp_billing",
                name="Send daily WhatsApp billing reminders",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=1800,
            )
            logger.info(
                "Scheduled WhatsApp billing campaign (%02d:%02d) provider=%s dry_run=%s require_confirmation=%s",
                settings.WHATSAPP_BILLING_HOUR,
                settings.WHATSAPP_BILLING_MINUTE,
                settings.WHATSAPP_BILLING_PROVIDER,
                settings.WHATSAPP_BILLING_DRY_RUN,
                getattr(settings, "WHATSAPP_BILLING_REQUIRE_CONFIRMATION", True),
            )
        elif settings.WHATSAPP_BILLING_ENABLED and not settings.WHATSAPP_FEATURE_ENABLED:
            logger.info(
                "WhatsApp billing configured but skipped: WHATSAPP_FEATURE_ENABLED=false (phase disabled)."
            )

        if settings.AI_EMPLOYEE_ENABLED and settings.AI_EMPLOYEE_DAILY_SUMMARY_ENABLED:
            ai_employee_job_func = daily_ai_employee_job
            if telegram_app and bool(getattr(settings, "AI_EMPLOYEE_TELEGRAM_ALERT_ENABLED", True)):
                async def daily_ai_employee_job_with_alert():
                    result = await daily_ai_employee_job()
                    await send_ai_employee_alert(telegram_app, result)
                    return result

                ai_employee_job_func = daily_ai_employee_job_with_alert

            scheduler.add_job(
                func=ai_employee_job_func,
                trigger=CronTrigger(
                    hour=int(getattr(settings, "AI_EMPLOYEE_DAILY_HOUR", 8)),
                    minute=int(getattr(settings, "AI_EMPLOYEE_DAILY_MINUTE", 20)),
                ),
                id="daily_ai_employee",
                name="Run AI Employee daily orchestration",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=1800,
            )
            logger.info(
                "Scheduled AI Employee orchestration (%02d:%02d) engine=%s dry_run=%s telegram_alert=%s",
                int(getattr(settings, "AI_EMPLOYEE_DAILY_HOUR", 8)),
                int(getattr(settings, "AI_EMPLOYEE_DAILY_MINUTE", 20)),
                getattr(settings, "AI_EMPLOYEE_ORCHESTRATION_ENGINE", "builtin"),
                getattr(settings, "AI_EMPLOYEE_DRY_RUN", True),
                bool(getattr(settings, "AI_EMPLOYEE_TELEGRAM_ALERT_ENABLED", True)),
            )
        elif settings.AI_EMPLOYEE_ENABLED:
            logger.info(
                "AI Employee enabled in manual mode (daily summary scheduler disabled)."
            )

        # Start the scheduler
        scheduler.start()
        logger.info("Background job scheduler started successfully")

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        raise

    # Start Telegram bot if configured
    if telegram_app:
        try:
            await start_bot(telegram_app)
            logger.info("Telegram bot is running")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            telegram_app = None

    yield  # Application runs here

    # Shutdown: Stop Telegram bot
    if telegram_app:
        try:
            await stop_bot(telegram_app)
            logger.info("Telegram bot stopped")
        except Exception as e:
            logger.error(f"Error stopping Telegram bot: {e}")

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
app.include_router(conversation.router, prefix="/api/conversation", tags=["conversation"], dependencies=[Depends(verify_api_key)])
app.include_router(clients.router, prefix="/api/clients", tags=["clients"], dependencies=[Depends(verify_api_key)])
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"], dependencies=[Depends(verify_api_key)])
app.include_router(signatures.router, prefix="/api/signatures", tags=["signatures"], dependencies=[Depends(verify_api_key)])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(verify_api_key)])
