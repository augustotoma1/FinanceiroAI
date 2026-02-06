"""
Background Jobs Module

This module contains background job definitions for automated synchronization
and scheduled tasks using APScheduler.

Background jobs include:
- Client synchronization from Conta Azul
- Financial data synchronization from Conta Azul
- Delinquency analysis
- Token refresh checks

All jobs are designed to run independently and handle their own error recovery.
"""

from app.background.sync_clients import sync_clients_job

__all__ = [
    "sync_clients_job",
]
