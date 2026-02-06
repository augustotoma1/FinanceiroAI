"""
Services Module

This module contains service clients for external API integrations:
- claude_service: Claude API integration for conversational AI
- conta_azul_service: Conta Azul OAuth2 client for accounting platform integration
- autentique_service: Autentique GraphQL client for electronic signatures
- contract_generator: Contract generation logic with PDF creation
- delinquency_analyzer: Payment analysis and risk scoring engine
"""

# Services will be imported here as they are implemented
from .claude_service import ClaudeService
from .conta_azul_service import ContaAzulService
from .autentique_service import AutentiqueService
from .contract_generator import ContractGenerator
from .delinquency_analyzer import DelinquencyAnalyzer
