"""
Background Jobs Module

This module contains background job definitions for automated synchronization
and scheduled tasks using APScheduler.

Background jobs include:
- Client synchronization from Conta Azul
- Financial data synchronization from Conta Azul
- Signature synchronization from Autentique
- Contract lifecycle maintenance and alerts
- Billing email reminders
- Billing WhatsApp reminders
- Delinquency analysis
- Token refresh checks

All jobs are designed to run independently and handle their own error recovery.
"""

from app.background.sync_clients import sync_clients_job
from app.background.sync_financial import sync_financial_job
from app.background.sync_signatures import sync_signatures_job
from app.background.contract_lifecycle import daily_contract_lifecycle_job
from app.background.email_billing import daily_billing_email_job
from app.background.whatsapp_billing import daily_whatsapp_billing_job
from app.background.ai_employee import daily_ai_employee_job

__all__ = [
    "sync_clients_job",
    "sync_financial_job",
    "sync_signatures_job",
    "daily_contract_lifecycle_job",
    "daily_billing_email_job",
    "daily_whatsapp_billing_job",
    "daily_ai_employee_job",
]
