"""
Claude API Service Client

This module provides a service client for interacting with Anthropic's Claude API
for conversational AI capabilities. Used primarily for conducting natural
conversations to collect contract data from users.

The service handles:
- Multi-turn conversational data collection
- System prompt configuration for guided responses
- Structured data extraction from conversations
- Error handling and retry logic for API calls

Usage:
    from app.services.claude_service import ClaudeService

    service = ClaudeService()
    result = await service.collect_contract_data(conversation_history)

    if result["complete"]:
        contract_data = result["data"]
        # Generate contract with collected data
"""

from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError
from app.config import settings
from typing import Dict, List, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)


class ClaudeService:
    """
    Service client for Anthropic Claude API integration.

    Provides methods for conversational AI interactions, specifically designed
    for collecting contract data through natural language conversations.

    The client automatically reads the API key from the ANTHROPIC_API_KEY
    environment variable (configured via app.config.settings).

    Attributes:
        client: Anthropic API client instance
        model: Claude model to use (default: claude-sonnet-4-20250514)
    """

    def __init__(self):
        """
        Initialize Claude API client.

        The Anthropic client automatically reads ANTHROPIC_API_KEY from the
        environment. Raises ValueError if the API key is not configured.
        """
        try:
            # Client auto-reads ANTHROPIC_API_KEY from environment
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            self.model = settings.ANTHROPIC_MODEL
            logger.info(f"Claude API service initialized with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize Claude API client: {e}")
            raise ValueError(f"Claude API initialization failed. Ensure ANTHROPIC_API_KEY is set: {e}")

    async def collect_contract_data(
        self,
        conversation_history: List[Dict[str, str]],
        max_tokens: int = 1024
    ) -> Dict[str, Any]:
        """
        Multi-turn conversation to collect all necessary contract data.

        Conducts a natural conversation with the user to gather all required
        information for generating a service contract. Returns structured data
        when collection is complete.

        Args:
            conversation_history: List of message dicts with "role" and "content" keys
                Example: [{"role": "user", "content": "I need a contract"}, ...]
            max_tokens: Maximum tokens for Claude's response (default: 1024)

        Returns:
            Dict with either:
                - {"complete": False, "message": "Next question from Claude"}
                - {"complete": True, "data": {...}} when all data collected

        Raises:
            ValueError: If conversation_history is empty or malformed
            APIError: If Claude API returns an error

        Example:
            >>> service = ClaudeService()
            >>> history = [{"role": "user", "content": "I need a new contract"}]
            >>> result = await service.collect_contract_data(history)
            >>> if not result["complete"]:
            ...     print(result["message"])  # Next question from Claude
        """
        if not conversation_history:
            raise ValueError("conversation_history cannot be empty")

        # Validate conversation history format
        for msg in conversation_history:
            if "role" not in msg or "content" not in msg:
                raise ValueError("Each message must have 'role' and 'content' keys")
            if msg["role"] not in ["user", "assistant"]:
                raise ValueError("Message role must be 'user' or 'assistant'")

        system_prompt = """You are a financial assistant helping collect information to generate a service contract.

You need to collect the following information:
- Client full name and CPF/CNPJ (Brazilian tax ID)
- Service description and scope
- Contract value (in Brazilian Real - BRL) and payment terms
- Start date and duration
- Special clauses or requirements

Ask questions naturally, one or two at a time. Be conversational and friendly.
When you have ALL required information, respond ONLY with valid JSON in this exact format:
{"complete": true, "data": {"client_name": "...", "cpf_cnpj": "...", "service_description": "...", "contract_value": 0.00, "payment_terms": "...", "start_date": "YYYY-MM-DD", "duration_months": 0, "special_clauses": "..."}}

Important:
- Do NOT include any text before or after the JSON
- Ensure the JSON is valid and properly formatted
- All fields are required before marking complete as true"""

        try:
            # Make API call to Claude
            logger.info(f"Sending conversation to Claude with {len(conversation_history)} messages")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=conversation_history
            )

            # Extract assistant's response
            assistant_message = response.content[0].text
            logger.debug(f"Claude response: {assistant_message[:100]}...")

            # Check if data collection is complete
            if '"complete": true' in assistant_message or '"complete":true' in assistant_message:
                try:
                    # Parse structured data from JSON response
                    data = json.loads(assistant_message)

                    # Validate the response structure
                    if not isinstance(data, dict) or "complete" not in data or "data" not in data:
                        logger.warning("Claude returned malformed completion response")
                        return {
                            "complete": False,
                            "message": "Please provide any remaining information."
                        }

                    logger.info("Contract data collection complete")
                    return data

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Claude's JSON response: {e}")
                    # Continue conversation if JSON parsing fails
                    return {
                        "complete": False,
                        "message": "Could you please confirm all the information again?"
                    }

            # Continue conversation
            return {
                "complete": False,
                "message": assistant_message
            }

        except RateLimitError as e:
            logger.error(f"Claude API rate limit exceeded: {e}")
            raise APIError(f"Rate limit exceeded. Please try again later: {e}")

        except APIConnectionError as e:
            logger.error(f"Failed to connect to Claude API: {e}")
            raise APIError(f"Connection error. Please check your network: {e}")

        except APIError as e:
            logger.error(f"Claude API error: {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error in collect_contract_data: {e}")
            raise APIError(f"Unexpected error: {e}")

    async def send_message(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Send a single message to Claude and get a response.

        General-purpose method for sending messages to Claude. Useful for
        one-off queries or custom conversation flows.

        Args:
            message: The user message to send
            system_prompt: Optional system prompt to guide Claude's behavior
            max_tokens: Maximum tokens for response (default: 1024)
            conversation_history: Optional previous conversation context

        Returns:
            Claude's text response

        Raises:
            APIError: If Claude API returns an error

        Example:
            >>> service = ClaudeService()
            >>> response = await service.send_message(
            ...     "Explain contract terms in simple language",
            ...     system_prompt="You are a legal assistant"
            ... )
        """
        try:
            # Build messages array
            messages = conversation_history or []
            messages.append({"role": "user", "content": message})

            logger.info(f"Sending single message to Claude")

            # Create API request parameters
            params = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages
            }

            # Add system prompt if provided
            if system_prompt:
                params["system"] = system_prompt

            response = self.client.messages.create(**params)

            # Extract and return text response
            return response.content[0].text

        except (RateLimitError, APIConnectionError, APIError) as e:
            logger.error(f"Claude API error in send_message: {e}")
            raise APIError(f"Failed to send message: {e}")

        except Exception as e:
            logger.error(f"Unexpected error in send_message: {e}")
            raise APIError(f"Unexpected error: {e}")

    def validate_collected_data(self, data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate that all required contract fields are present and valid.

        Args:
            data: Dictionary of collected contract data

        Returns:
            Tuple of (is_valid: bool, errors: List[str])

        Example:
            >>> service = ClaudeService()
            >>> is_valid, errors = service.validate_collected_data(data)
            >>> if not is_valid:
            ...     print("Missing fields:", errors)
        """
        required_fields = [
            "client_name",
            "cpf_cnpj",
            "service_description",
            "contract_value",
            "payment_terms",
            "start_date",
            "duration_months"
        ]

        errors = []

        for field in required_fields:
            if field not in data or not data[field]:
                errors.append(f"Missing required field: {field}")

        # Additional validation
        if "contract_value" in data:
            try:
                value = float(data["contract_value"])
                if value <= 0:
                    errors.append("contract_value must be greater than zero")
            except (ValueError, TypeError):
                errors.append("contract_value must be a valid number")

        if "duration_months" in data:
            try:
                duration = int(data["duration_months"])
                if duration <= 0:
                    errors.append("duration_months must be greater than zero")
            except (ValueError, TypeError):
                errors.append("duration_months must be a valid integer")

        return len(errors) == 0, errors
