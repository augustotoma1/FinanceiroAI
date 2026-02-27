"""
Unit tests for Claude API Service

Tests cover:
- Service initialization and configuration
- Conversational data collection workflow
- Message sending and response handling
- Data validation logic
- Error handling and API failures
- Edge cases and malformed responses
"""

import pytest
import json
import httpx
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from anthropic import APIError, APIConnectionError, RateLimitError

from app.services.claude_service import ClaudeService
from app.config import settings


# ── Helper factories for anthropic SDK exceptions ───────────────────────────
# The SDK exceptions require httpx objects, not just a string message.

def _make_api_error(message: str = "API error") -> APIError:
    """Create a properly-constructed APIError for tests."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return APIError(message, request=request, body=None)


def _make_rate_limit_error(message: str = "Rate limit exceeded") -> RateLimitError:
    """Create a properly-constructed RateLimitError for tests."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request)
    return RateLimitError(message, response=response, body=None)


def _make_connection_error(message: str = "Connection failed") -> APIConnectionError:
    """Create a properly-constructed APIConnectionError for tests."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return APIConnectionError(message=message, request=request)


class TestClaudeServiceInitialization:
    """Test Claude service initialization and configuration"""

    def test_initialization_success(self):
        """Test successful service initialization with valid API key"""
        with patch('app.services.claude_service.Anthropic') as mock_anthropic:
            service = ClaudeService()

            assert service.client is not None
            assert service.model == settings.ANTHROPIC_MODEL
            mock_anthropic.assert_called_once_with(api_key=settings.ANTHROPIC_API_KEY)

    def test_initialization_without_api_key(self):
        """Test that initialization fails without API key"""
        with patch('app.config.settings.ANTHROPIC_API_KEY', ''):
            with patch('app.services.claude_service.Anthropic', side_effect=Exception("API key required")):
                with pytest.raises(ValueError, match="Claude API initialization failed"):
                    ClaudeService()

    def test_initialization_with_invalid_api_key(self):
        """Test initialization with invalid API key format"""
        with patch('app.services.claude_service.Anthropic', side_effect=Exception("Invalid API key")):
            with pytest.raises(ValueError, match="Claude API initialization failed"):
                ClaudeService()


class TestCollectContractData:
    """Test contract data collection workflow"""

    @pytest.fixture
    def service(self):
        """Create a ClaudeService instance for testing"""
        with patch('app.services.claude_service.Anthropic'):
            return ClaudeService()

    @pytest.mark.asyncio
    async def test_collect_data_conversation_continues(self, service):
        """Test conversation continues when data collection is incomplete"""
        conversation_history = [
            {"role": "user", "content": "I need a new contract"}
        ]

        # Mock Claude API response
        mock_response = Mock()
        mock_response.content = [Mock(text="Great! Can you tell me the client's full name?")]
        service.client.messages.create = Mock(return_value=mock_response)

        result = await service.collect_contract_data(conversation_history)

        assert result["complete"] is False
        assert "message" in result
        assert "full name" in result["message"].lower()

        # Verify API call was made with correct parameters
        service.client.messages.create.assert_called_once()
        call_kwargs = service.client.messages.create.call_args[1]
        assert call_kwargs["model"] == settings.ANTHROPIC_MODEL
        assert call_kwargs["messages"] == conversation_history
        assert "system" in call_kwargs

    @pytest.mark.asyncio
    async def test_collect_data_completion_with_valid_json(self, service):
        """Test successful data collection with complete JSON response"""
        conversation_history = [
            {"role": "user", "content": "I need a new contract"},
            {"role": "assistant", "content": "Great! Can you tell me the client's full name?"},
            {"role": "user", "content": "João Silva, CPF 123.456.789-00"}
        ]

        complete_data = {
            "complete": True,
            "data": {
                "client_name": "João Silva",
                "cpf_cnpj": "123.456.789-00",
                "service_description": "Consultoria financeira",
                "contract_value": 5000.00,
                "payment_terms": "Mensal",
                "start_date": "2026-03-01",
                "duration_months": 12,
                "special_clauses": "Reajuste anual pelo IPCA"
            }
        }

        # Mock Claude API response with complete JSON
        mock_response = Mock()
        mock_response.content = [Mock(text=json.dumps(complete_data))]
        service.client.messages.create = Mock(return_value=mock_response)

        result = await service.collect_contract_data(conversation_history)

        assert result["complete"] is True
        assert "data" in result
        assert result["data"]["client_name"] == "João Silva"
        assert result["data"]["cpf_cnpj"] == "123.456.789-00"
        assert result["data"]["contract_value"] == 5000.00

    @pytest.mark.asyncio
    async def test_collect_data_malformed_json_response(self, service):
        """Test handling of malformed JSON when marked as complete"""
        conversation_history = [
            {"role": "user", "content": "All information provided"}
        ]

        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.content = [Mock(text='{"complete": true, "data": invalid json}')]
        service.client.messages.create = Mock(return_value=mock_response)

        result = await service.collect_contract_data(conversation_history)

        # Should fall back to continuing conversation
        assert result["complete"] is False
        assert "message" in result

    @pytest.mark.asyncio
    async def test_collect_data_incomplete_json_structure(self, service):
        """Test handling of JSON response without required fields"""
        conversation_history = [
            {"role": "user", "content": "All information provided"}
        ]

        # Mock response with incomplete JSON structure
        mock_response = Mock()
        mock_response.content = [Mock(text='{"complete": true}')]  # Missing "data" field
        service.client.messages.create = Mock(return_value=mock_response)

        result = await service.collect_contract_data(conversation_history)

        # Should fall back to continuing conversation
        assert result["complete"] is False
        assert "message" in result

    @pytest.mark.asyncio
    async def test_collect_data_empty_history_raises_error(self, service):
        """Test that empty conversation history raises ValueError"""
        with pytest.raises(ValueError, match="conversation_history cannot be empty"):
            await service.collect_contract_data([])

    @pytest.mark.asyncio
    async def test_collect_data_invalid_message_format(self, service):
        """Test that invalid message format raises ValueError"""
        invalid_history = [
            {"content": "Missing role key"}  # Missing "role"
        ]

        with pytest.raises(ValueError, match="must have 'role' and 'content' keys"):
            await service.collect_contract_data(invalid_history)

    @pytest.mark.asyncio
    async def test_collect_data_invalid_role(self, service):
        """Test that invalid role raises ValueError"""
        invalid_history = [
            {"role": "system", "content": "Invalid role"}  # Should be user or assistant
        ]

        with pytest.raises(ValueError, match="role must be 'user' or 'assistant'"):
            await service.collect_contract_data(invalid_history)

    @pytest.mark.asyncio
    async def test_collect_data_rate_limit_error(self, service):
        """Test handling of API rate limit error — re-raised as-is"""
        conversation_history = [
            {"role": "user", "content": "Test message"}
        ]

        service.client.messages.create = Mock(side_effect=_make_rate_limit_error())

        with pytest.raises(RateLimitError):
            await service.collect_contract_data(conversation_history)

    @pytest.mark.asyncio
    async def test_collect_data_connection_error(self, service):
        """Test handling of API connection error — re-raised as-is"""
        conversation_history = [
            {"role": "user", "content": "Test message"}
        ]

        service.client.messages.create = Mock(side_effect=_make_connection_error())

        with pytest.raises(APIConnectionError):
            await service.collect_contract_data(conversation_history)

    @pytest.mark.asyncio
    async def test_collect_data_generic_api_error(self, service):
        """Test handling of generic API error — re-raised as-is"""
        conversation_history = [
            {"role": "user", "content": "Test message"}
        ]

        service.client.messages.create = Mock(side_effect=_make_api_error())

        with pytest.raises(APIError):
            await service.collect_contract_data(conversation_history)

    @pytest.mark.asyncio
    async def test_collect_data_unexpected_error(self, service):
        """Test handling of unexpected error — wrapped in ValueError"""
        conversation_history = [
            {"role": "user", "content": "Test message"}
        ]

        service.client.messages.create = Mock(side_effect=Exception("Unexpected error"))

        with pytest.raises(ValueError, match="Unexpected error"):
            await service.collect_contract_data(conversation_history)

    @pytest.mark.asyncio
    async def test_collect_data_with_custom_max_tokens(self, service):
        """Test that custom max_tokens parameter is used"""
        conversation_history = [
            {"role": "user", "content": "Test message"}
        ]

        mock_response = Mock()
        mock_response.content = [Mock(text="Response")]
        service.client.messages.create = Mock(return_value=mock_response)

        await service.collect_contract_data(conversation_history, max_tokens=2048)

        call_kwargs = service.client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 2048

    @pytest.mark.asyncio
    async def test_collect_data_supports_async_sdk_response(self, service):
        """Test collect_contract_data works when SDK returns coroutine."""
        conversation_history = [{"role": "user", "content": "I need a contract"}]
        mock_response = Mock()
        mock_response.content = [Mock(text="Great! What's the client name?")]

        async def async_create(**kwargs):
            return mock_response

        service.client.messages.create = async_create

        result = await service.collect_contract_data(conversation_history)
        assert result["complete"] is False
        assert "client" in result["message"].lower()


class TestSendMessage:
    """Test general message sending functionality"""

    @pytest.fixture
    def service(self):
        """Create a ClaudeService instance for testing"""
        with patch('app.services.claude_service.Anthropic'):
            return ClaudeService()

    @pytest.mark.asyncio
    async def test_send_message_simple(self, service):
        """Test sending a simple message"""
        mock_response = Mock()
        mock_response.content = [Mock(text="This is a response")]
        service.client.messages.create = Mock(return_value=mock_response)

        response = await service.send_message("Hello Claude")

        assert response == "This is a response"
        service.client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_with_system_prompt(self, service):
        """Test sending message with custom system prompt"""
        mock_response = Mock()
        mock_response.content = [Mock(text="Legal advice response")]
        service.client.messages.create = Mock(return_value=mock_response)

        system_prompt = "You are a legal assistant"
        response = await service.send_message(
            "Explain contract terms",
            system_prompt=system_prompt
        )

        assert response == "Legal advice response"
        call_kwargs = service.client.messages.create.call_args[1]
        assert call_kwargs["system"] == system_prompt

    @pytest.mark.asyncio
    async def test_send_message_with_conversation_history(self, service):
        """Test sending message with conversation context"""
        mock_response = Mock()
        mock_response.content = [Mock(text="Follow-up response")]
        service.client.messages.create = Mock(return_value=mock_response)

        history = [
            {"role": "user", "content": "Previous message"},
            {"role": "assistant", "content": "Previous response"}
        ]

        response = await service.send_message(
            "Follow-up question",
            conversation_history=history
        )

        assert response == "Follow-up response"
        call_kwargs = service.client.messages.create.call_args[1]
        assert len(call_kwargs["messages"]) == 3  # History + new message

    @pytest.mark.asyncio
    async def test_send_message_with_custom_max_tokens(self, service):
        """Test sending message with custom max_tokens"""
        mock_response = Mock()
        mock_response.content = [Mock(text="Response")]
        service.client.messages.create = Mock(return_value=mock_response)

        await service.send_message("Test", max_tokens=2048)

        call_kwargs = service.client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 2048

    @pytest.mark.asyncio
    async def test_send_message_api_error(self, service):
        """Test handling of API error during message send — re-raised as-is"""
        service.client.messages.create = Mock(side_effect=_make_api_error())

        with pytest.raises(APIError):
            await service.send_message("Test message")

    @pytest.mark.asyncio
    async def test_send_message_connection_error(self, service):
        """Test handling of connection error during message send — re-raised as-is"""
        service.client.messages.create = Mock(side_effect=_make_connection_error())

        with pytest.raises(APIConnectionError):
            await service.send_message("Test message")

    @pytest.mark.asyncio
    async def test_send_message_rate_limit_error(self, service):
        """Test handling of rate limit error during message send — re-raised as-is"""
        service.client.messages.create = Mock(side_effect=_make_rate_limit_error())

        with pytest.raises(RateLimitError):
            await service.send_message("Test message")

    @pytest.mark.asyncio
    async def test_send_message_unexpected_error(self, service):
        """Test handling of unexpected error during message send — wrapped in ValueError"""
        service.client.messages.create = Mock(side_effect=Exception("Unexpected"))

        with pytest.raises(ValueError, match="Unexpected error"):
            await service.send_message("Test message")

    @pytest.mark.asyncio
    async def test_send_message_supports_async_sdk_response(self, service):
        """Test send_message works when SDK returns coroutine."""
        mock_response = Mock()
        mock_response.content = [Mock(text="Async response")]

        async def async_create(**kwargs):
            return mock_response

        service.client.messages.create = async_create

        response = await service.send_message("Hello Claude")
        assert response == "Async response"

    @pytest.mark.asyncio
    async def test_send_message_fallback_to_openai_after_provider_failures(self, service):
        """Test fallback chain reaches OpenAI when Gemini/Claude fail."""
        service.provider = "gemini"
        service._fallback_candidates = Mock(return_value=["gemini", "anthropic", "openai"])
        service._get_provider_client = Mock(return_value=object())
        service._gemini_generate = AsyncMock(side_effect=ValueError("gemini down"))
        service._anthropic_send = AsyncMock(side_effect=ValueError("claude down"))
        service._openai_generate = AsyncMock(return_value="openai fallback ok")

        result = await service.send_message("hello")

        assert result == "openai fallback ok"
        service._gemini_generate.assert_awaited_once()
        service._anthropic_send.assert_awaited_once()
        service._openai_generate.assert_awaited_once()


class TestValidateCollectedData:
    """Test data validation functionality"""

    @pytest.fixture
    def service(self):
        """Create a ClaudeService instance for testing"""
        with patch('app.services.claude_service.Anthropic'):
            return ClaudeService()

    def test_validate_complete_valid_data(self, service):
        """Test validation of complete and valid contract data"""
        valid_data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria financeira",
            "contract_value": 5000.00,
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 12,
            "special_clauses": "Reajuste anual"
        }

        is_valid, errors = service.validate_collected_data(valid_data)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_missing_required_field(self, service):
        """Test validation fails when required field is missing"""
        incomplete_data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            # Missing other required fields
        }

        is_valid, errors = service.validate_collected_data(incomplete_data)

        assert is_valid is False
        assert len(errors) > 0
        assert any("service_description" in error for error in errors)

    def test_validate_empty_required_field(self, service):
        """Test validation fails when required field is empty"""
        data_with_empty_field = {
            "client_name": "",  # Empty string
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": 5000.00,
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 12
        }

        is_valid, errors = service.validate_collected_data(data_with_empty_field)

        assert is_valid is False
        assert any("client_name" in error for error in errors)

    def test_validate_invalid_contract_value_zero(self, service):
        """Test validation fails for zero contract value"""
        data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": 0,  # Invalid: must be > 0
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 12
        }

        is_valid, errors = service.validate_collected_data(data)

        assert is_valid is False
        assert any("contract_value" in error and "greater than zero" in error for error in errors)

    def test_validate_invalid_contract_value_negative(self, service):
        """Test validation fails for negative contract value"""
        data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": -100,  # Invalid: negative value
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 12
        }

        is_valid, errors = service.validate_collected_data(data)

        assert is_valid is False
        assert any("contract_value" in error and "greater than zero" in error for error in errors)

    def test_validate_invalid_contract_value_non_numeric(self, service):
        """Test validation fails for non-numeric contract value"""
        data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": "not a number",  # Invalid: not numeric
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 12
        }

        is_valid, errors = service.validate_collected_data(data)

        assert is_valid is False
        assert any("contract_value" in error and "valid number" in error for error in errors)

    def test_validate_invalid_duration_zero(self, service):
        """Test validation fails for zero duration"""
        data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": 5000.00,
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 0  # Invalid: must be > 0
        }

        is_valid, errors = service.validate_collected_data(data)

        assert is_valid is False
        assert any("duration_months" in error and "greater than zero" in error for error in errors)

    def test_validate_invalid_duration_non_integer(self, service):
        """Test validation fails for non-integer duration"""
        data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": 5000.00,
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": "twelve"  # Invalid: not an integer
        }

        is_valid, errors = service.validate_collected_data(data)

        assert is_valid is False
        assert any("duration_months" in error and "valid integer" in error for error in errors)

    def test_validate_contract_value_as_string_number(self, service):
        """Test validation accepts string representation of valid number"""
        data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": "5000.00",  # String but valid number
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 12
        }

        is_valid, errors = service.validate_collected_data(data)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_duration_as_string_integer(self, service):
        """Test validation accepts string representation of valid integer"""
        data = {
            "client_name": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": 5000.00,
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": "12"  # String but valid integer
        }

        is_valid, errors = service.validate_collected_data(data)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_multiple_errors(self, service):
        """Test validation returns all errors for multiple invalid fields"""
        invalid_data = {
            "client_name": "",  # Empty
            "cpf_cnpj": "123.456.789-00",
            "service_description": "Consultoria",
            "contract_value": -100,  # Negative
            "payment_terms": "Mensal",
            "start_date": "2026-03-01",
            "duration_months": 0  # Zero
        }

        is_valid, errors = service.validate_collected_data(invalid_data)

        assert is_valid is False
        assert len(errors) >= 3  # At least 3 errors
        assert any("client_name" in error for error in errors)
        assert any("contract_value" in error for error in errors)
        assert any("duration_months" in error for error in errors)
