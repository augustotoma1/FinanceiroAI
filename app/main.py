"""
FastAPI Application Entry Point

This module initializes the FastAPI application for the Financial Automation System.
It configures CORS, includes API routers, and provides health check endpoint for monitoring.

The application serves as the integration hub for:
- Claude AI conversational data collection
- Conta Azul accounting platform synchronization
- Autentique electronic signature workflow
- Delinquency analysis and monitoring
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# Initialize FastAPI application with metadata
app = FastAPI(
    title="Financial Automation System",
    description="AI-powered financial automation with Conta Azul and Autentique integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
from app.api import conversation, clients, contracts, signatures, auth

# Include routers with prefixes and tags
app.include_router(conversation.router, prefix="/api/conversation", tags=["conversation"])
app.include_router(clients.router, prefix="/api/clients", tags=["clients"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
app.include_router(signatures.router, prefix="/api/signatures", tags=["signatures"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])

# Additional routers to be added as they are implemented:
# from app.api import dashboard
# app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
