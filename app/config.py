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

    # Conta Azul API Configuration (OAuth 2.0)
    CONTA_AZUL_CLIENT_ID: str  # Required - no default for security
    CONTA_AZUL_CLIENT_SECRET: str  # Required - no default for security
    CONTA_AZUL_REDIRECT_URI: str  # Required - must match OAuth app configuration
    CONTA_AZUL_API_BASE_URL: str = "https://api.contaazul.com"

    # Autentique API Configuration (GraphQL)
    AUTENTIQUE_API_KEY: str  # Required - no default for security
    AUTENTIQUE_API_URL: str = "https://api.autentique.com.br/v2/graphql"
    AUTENTIQUE_RATE_LIMIT: int = 60  # requests per minute

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables not defined in model
    )


# Global settings instance
# This will be imported by other modules to access configuration
settings = Settings()
