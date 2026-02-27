"""
Configuration Management with Pydantic Settings

This module provides centralized configuration management for the Financial Automation
System. All settings are loaded from environment variables with validation and type
checking. Supports loading from .env files for development.

Environment variables are case-sensitive and should match the field names exactly.
Required fields without defaults will raise validation errors if not provided.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """
    Application settings with automatic environment variable loading.

    Settings are loaded with the following priority (highest to lowest):
    1. Environment variables
    2. .env file (if present)
    3. Default values defined below

    All sensitive credentials (API keys, secrets) must be provided via environment
    variables - they have no defaults for security reasons.
    """

    # Application Configuration
    APP_NAME: str = "Financial Automation System"
    DEBUG: bool = False
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Database Configuration
    DATABASE_URL: str = "postgresql://user:password@localhost/financial_automation"

    # Anthropic Claude API Configuration
    ANTHROPIC_API_KEY: str  # Required - no default for security
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    AI_PROVIDER: str = "anthropic"  # anthropic | gemini
    GOOGLE_API_KEY: str = ""  # Optional fallback key for Gemini provider
    GEMINI_API_KEY: str = ""  # Preferred key for Gemini provider
    GEMINI_MODEL: str = "gemini-2.0-flash"
    OPENAI_API_KEY: str = ""  # Optional fallback key for OpenAI provider
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Conta Azul API Configuration (OAuth 2.0)
    CONTA_AZUL_CLIENT_ID: str  # Required - no default for security
    CONTA_AZUL_CLIENT_SECRET: str  # Required - no default for security
    CONTA_AZUL_REDIRECT_URI: str  # Required - must match OAuth app configuration
    CONTA_AZUL_API_BASE_URL: str = "https://api.contaazul.com"

    # Autentique API Configuration (GraphQL)
    AUTENTIQUE_API_KEY: str  # Required - no default for security
    AUTENTIQUE_API_URL: str = "https://api.autentique.com.br/v2/graphql"
    AUTENTIQUE_RATE_LIMIT: int = 60  # requests per minute

    # API Authentication
    API_SECRET_KEY: str  # Required - used to authenticate API requests via X-API-Key header

    # Conversation lifecycle
    CONVERSATION_TTL_HOURS: int = 24  # Expire idle conversation sessions after this many hours

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN: str = ""  # Optional - empty means bot disabled
    TELEGRAM_ALERT_CHAT_IDS: str = ""  # Comma-separated chat IDs for daily CFO alerts
    TELEGRAM_ALERT_HOUR: int = 8
    TELEGRAM_ALERT_MINUTE: int = 0
    TELEGRAM_WEEKLY_ALERT_ENABLED: bool = True
    TELEGRAM_WEEKLY_ALERT_DAY: str = "mon"  # APScheduler format (mon,tue,...)
    TELEGRAM_WEEKLY_ALERT_HOUR: int = 8
    TELEGRAM_WEEKLY_ALERT_MINUTE: int = 5

    # AI Employee orchestration (CrewAI + LangGraph roadmap)
    AI_EMPLOYEE_ENABLED: bool = False
    AI_EMPLOYEE_DRY_RUN: bool = True
    AI_EMPLOYEE_ORCHESTRATION_ENGINE: str = "auto"  # auto prefers langgraph, then crewai, then builtin
    AI_EMPLOYEE_CREW_ENABLED: bool = False  # Enable CrewAI orchestration mode
    AI_EMPLOYEE_CREW_EXECUTION_ENABLED: bool = False  # Execute native CrewAI kickoff (otherwise planning_only)
    AI_EMPLOYEE_CREW_MAX_ITERATIONS: int = 6
    AI_EMPLOYEE_DAILY_SUMMARY_ENABLED: bool = False
    AI_EMPLOYEE_DAILY_HOUR: int = 8
    AI_EMPLOYEE_DAILY_MINUTE: int = 20
    AI_EMPLOYEE_TELEGRAM_ALERT_ENABLED: bool = True
    AI_EMPLOYEE_MAX_ACTIONS_PER_RUN: int = 50
    AI_EMPLOYEE_ENABLE_EMAIL_PREVIEW: bool = True
    AI_EMPLOYEE_ENABLE_WHATSAPP_PREVIEW: bool = False
    AI_EMPLOYEE_OPERATION_TIMEOUT_SECONDS: int = 120
    AI_EMPLOYEE_LOG_ACTIONS: bool = True

    # Contract lifecycle automation
    CONTRACT_LIFECYCLE_ENABLED: bool = True
    CONTRACT_LIFECYCLE_ALERT_ENABLED: bool = True
    CONTRACT_LIFECYCLE_ALERT_DAYS: int = 30
    CONTRACT_LIFECYCLE_RUN_HOUR: int = 7
    CONTRACT_LIFECYCLE_RUN_MINUTE: int = 45
    CONTRACT_LIFECYCLE_ALERT_HOUR: int = 8
    CONTRACT_LIFECYCLE_ALERT_MINUTE: int = 10

    # Autentique signature sync automation
    AUTENTIQUE_SIGNATURE_SYNC_ENABLED: bool = True
    AUTENTIQUE_SIGNATURE_SYNC_INTERVAL_MINUTES: int = 30
    AUTENTIQUE_SIGNATURE_SYNC_MAX_CONTRACTS: int = 100
    AUTENTIQUE_SIGNATURE_SYNC_ONLY_OPEN: bool = True
    AUTENTIQUE_WEBHOOK_ENABLED: bool = True
    AUTENTIQUE_WEBHOOK_SECRET: str = ""
    AUTENTIQUE_WEBHOOK_FALLBACK_MAX_CONTRACTS: int = 20

    # Billing Email Campaign (Phase 1 expansion)
    EMAIL_BILLING_ENABLED: bool = False
    EMAIL_BILLING_PROVIDER: str = "log"  # log | sendgrid
    EMAIL_BILLING_FROM: str = ""
    EMAIL_BILLING_REPLY_TO: str = ""
    SENDGRID_API_KEY: str = ""
    EMAIL_BILLING_DRY_RUN: bool = True
    EMAIL_BILLING_TEST_RECIPIENTS: str = ""  # comma-separated emails for test-only routing
    EMAIL_BILLING_REAL_SEND_ENABLED: bool = False  # hard safety lock for real email dispatch
    EMAIL_BILLING_ALERT_ENABLED: bool = True  # Send daily campaign summary to Telegram alert chats
    EMAIL_BILLING_HOUR: int = 9
    EMAIL_BILLING_MINUTE: int = 0
    EMAIL_BILLING_DUE_SOON_DAYS: int = 3
    EMAIL_BILLING_OVERDUE_MAX_DAYS: int = 30
    EMAIL_BILLING_MAX_EMAILS_PER_RUN: int = 200

    # WhatsApp Billing Campaign (Phase 2 expansion)
    WHATSAPP_FEATURE_ENABLED: bool = False  # Keep disabled until final rollout phase
    WHATSAPP_BILLING_ENABLED: bool = False
    WHATSAPP_BILLING_PROVIDER: str = "log"  # log | waha
    WHATSAPP_BILLING_REQUIRE_CONFIRMATION: bool = True  # Block automatic scheduled send unless explicitly disabled
    WHATSAPP_BILLING_DRY_RUN: bool = True
    WHATSAPP_BILLING_HOUR: int = 10
    WHATSAPP_BILLING_MINUTE: int = 0
    WHATSAPP_BILLING_DUE_SOON_DAYS: int = 3
    WHATSAPP_BILLING_OVERDUE_MAX_DAYS: int = 30
    WHATSAPP_BILLING_MAX_MESSAGES_PER_RUN: int = 200
    WHATSAPP_BILLING_SKIP_NO_LID: bool = True
    WHATSAPP_BILLING_NO_LID_COOLDOWN_DAYS: int = 30
    WHATSAPP_WAHA_URL: str = ""
    WHATSAPP_WAHA_API_KEY: str = ""
    WHATSAPP_WAHA_SESSION: str = "default"

    # Legal knowledge grounding (contract/legal assistant)
    LEGAL_KNOWLEDGE_ENABLED: bool = True
    LEGAL_KNOWLEDGE_PATH: str = "app/knowledge/legal/sources.json"
    LEGAL_KNOWLEDGE_MAX_SNIPPETS: int = 3
    LEGAL_KNOWLEDGE_MIN_SCORE: int = 1

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables not defined in model
    )


# Global settings instance
# This will be imported by other modules to access configuration
settings = Settings()
