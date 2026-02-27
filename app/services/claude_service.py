"""
AI Service Client (Anthropic, Gemini, OpenAI)

This module provides a unified service client for conversational AI capabilities.
It supports multi-provider failover so operations can continue when one provider
is unavailable.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError

from app.config import settings

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = {"anthropic", "gemini", "openai"}


class ClaudeService:
    """
    Unified AI service used by conversation and bot flows.

    Provider selection:
    - Primary provider is `settings.AI_PROVIDER`.
    - Runtime fallback order appends remaining providers and tries available
      credentials in order.
    """

    def __init__(self):
        self.provider = (settings.AI_PROVIDER or "anthropic").strip().lower()
        if self.provider not in _SUPPORTED_PROVIDERS:
            logger.warning("Unknown AI_PROVIDER '%s'; using anthropic", self.provider)
            self.provider = "anthropic"

        self._clients: Dict[str, Any] = {}
        self.client: Any = None
        self.model = ""

        # Initialize primary provider eagerly for early misconfiguration detection.
        try:
            self.client = self._get_provider_client(self.provider)
            self.model = self._get_provider_model(self.provider)
            logger.info("AI service initialized: %s (%s)", self.provider, self.model)
        except Exception as exc:
            # If no fallback provider is configured, fail-fast.
            if not self._fallback_candidates(exclude_primary=True):
                if self.provider == "anthropic":
                    raise ValueError(
                        f"Claude API initialization failed. Ensure ANTHROPIC_API_KEY is set: {exc}"
                    )
                if self.provider == "gemini":
                    raise ValueError(
                        f"Gemini API initialization failed. Ensure GEMINI_API_KEY is set: {exc}"
                    )
                raise ValueError(f"AI provider initialization failed ({self.provider}): {exc}")
            logger.warning(
                "Primary AI provider initialization failed (%s). Fallback providers will be used. Error: %s",
                self.provider,
                exc,
            )

    def _get_provider_model(self, provider: str) -> str:
        if provider == "anthropic":
            return settings.ANTHROPIC_MODEL
        if provider == "gemini":
            return settings.GEMINI_MODEL
        if provider == "openai":
            return settings.OPENAI_MODEL
        return ""

    def _has_provider_credentials(self, provider: str) -> bool:
        if provider == "anthropic":
            return bool((settings.ANTHROPIC_API_KEY or "").strip())
        if provider == "gemini":
            return bool((settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY or "").strip())
        if provider == "openai":
            return bool((settings.OPENAI_API_KEY or "").strip())
        return False

    def _fallback_candidates(self, exclude_primary: bool = False) -> List[str]:
        # Preferred fallback policy requested by user: gemini -> anthropic -> openai.
        base_order = [self.provider, "gemini", "anthropic", "openai"]
        seen = set()
        ordered: List[str] = []
        for provider in base_order:
            if provider in seen:
                continue
            seen.add(provider)
            if not self._has_provider_credentials(provider):
                continue
            ordered.append(provider)

        if exclude_primary:
            return [p for p in ordered if p != self.provider]
        return ordered

    def _get_provider_client(self, provider: str) -> Any:
        if provider in self._clients:
            return self._clients[provider]

        if provider == "anthropic":
            api_key = (settings.ANTHROPIC_API_KEY or "").strip()
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is not configured")
            client = Anthropic(api_key=api_key)
            self._clients[provider] = client
            return client

        if provider == "gemini":
            import google.generativeai as genai  # type: ignore

            gemini_key = (settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY or "").strip()
            if not gemini_key:
                raise ValueError("GEMINI_API_KEY/GOOGLE_API_KEY is not configured")

            genai.configure(api_key=gemini_key)
            client = genai.GenerativeModel(settings.GEMINI_MODEL)
            self._clients[provider] = client
            return client

        if provider == "openai":
            # OpenAI client is implemented through HTTPX calls.
            self._clients[provider] = None
            return None

        raise ValueError(f"Unsupported AI provider: {provider}")

    async def _resolve_response(self, response_or_awaitable: Any) -> Any:
        """
        Support both sync and async SDK responses.
        """
        if inspect.isawaitable(response_or_awaitable):
            return await response_or_awaitable
        return response_or_awaitable

    async def _run_with_fallback(
        self,
        operation_name: str,
        runner: Callable[[str], Awaitable[str]],
    ) -> str:
        providers = self._fallback_candidates()
        if not providers:
            raise ValueError("No AI provider credentials configured")

        last_error: Optional[Exception] = None

        for idx, provider in enumerate(providers):
            try:
                _ = self._get_provider_client(provider)
                text = await runner(provider)
                if idx > 0:
                    logger.warning(
                        "AI fallback activated for %s: using provider '%s'",
                        operation_name,
                        provider,
                    )
                return text
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "AI provider '%s' failed in %s: %s",
                    provider,
                    operation_name,
                    exc,
                )

        if last_error is not None:
            raise last_error
        raise ValueError("Failed to get AI response")

    def _build_gemini_prompt(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        chunks: List[str] = []
        if system_prompt:
            chunks.append(f"SYSTEM:\n{system_prompt}")

        for msg in conversation_history or []:
            role = "Usuario" if msg.get("role") == "user" else "Assistente"
            chunks.append(f"{role}: {msg.get('content', '')}")

        chunks.append(f"Usuario: {message}")
        chunks.append("Assistente:")
        return "\n\n".join(chunks)

    def _extract_gemini_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            collected: List[str] = []
            for part in parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str):
                    collected.append(part_text)
            if collected:
                return "\n".join(collected).strip()

        return ""

    async def _gemini_generate(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 1024,
    ) -> str:
        prompt = self._build_gemini_prompt(
            message=message,
            system_prompt=system_prompt,
            conversation_history=conversation_history,
        )
        generation_config = {"max_output_tokens": max_tokens}

        client = self._get_provider_client("gemini")
        response = await asyncio.to_thread(
            client.generate_content,
            prompt,
            generation_config=generation_config,
        )

        text = self._extract_gemini_text(response)
        if not text:
            raise ValueError("Empty response from Gemini API")
        return text

    def _extract_openai_text(self, payload: Dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""

        content = (choices[0] or {}).get("message", {}).get("content", "")
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            return "\n".join(parts).strip()

        return ""

    async def _openai_generate(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 1024,
    ) -> str:
        api_key = (settings.OPENAI_API_KEY or "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        for msg in conversation_history or []:
            role = msg.get("role")
            content = msg.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:
            snippet = response.text[:300]
            raise ValueError(f"OpenAI API request failed: {response.status_code} - {snippet}")

        data = response.json()
        text = self._extract_openai_text(data)
        if not text:
            raise ValueError("Empty response from OpenAI API")
        return text

    async def _anthropic_collect(
        self,
        conversation_history: List[Dict[str, str]],
        system_prompt: str,
        max_tokens: int,
    ) -> str:
        client = self._get_provider_client("anthropic")
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=conversation_history,
        )
        response = await self._resolve_response(response)
        return response.content[0].text

    async def _anthropic_send(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        client = self._get_provider_client("anthropic")
        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": message})

        params: Dict[str, Any] = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system_prompt:
            params["system"] = system_prompt

        response = client.messages.create(**params)
        response = await self._resolve_response(response)
        return response.content[0].text

    async def collect_contract_data(
        self,
        conversation_history: List[Dict[str, str]],
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """
        Multi-turn conversation to collect all necessary contract data.

        Returns either:
        - {"complete": False, "message": "..."}
        - {"complete": True, "data": {...}}
        """
        if not conversation_history:
            raise ValueError("conversation_history cannot be empty")

        for msg in conversation_history:
            if "role" not in msg or "content" not in msg:
                raise ValueError("Each message must have 'role' and 'content' keys")
            if msg["role"] not in ["user", "assistant"]:
                raise ValueError("Message role must be 'user' or 'assistant'")

        system_prompt = """Você é um assistente financeiro que coleta informações para gerar contrato de prestação de serviços.

Regras de linguagem:
- Responda sempre em português brasileiro (pt-BR)
- Não misture inglês
- Não use emojis
- Seja claro, objetivo e cordial

Regras de confiabilidade:
- Nunca invente dados do cliente, cláusulas, leis, artigos ou jurisprudência
- Nunca preencha campos obrigatórios por suposição
- Se faltar informação, faça pergunta objetiva para coletar o dado correto
- Se o usuário pedir base jurídica e não houver certeza, informe que precisa de validação jurídica humana

Você precisa coletar:
- Nome completo do cliente e CPF/CNPJ
- Descrição e escopo do serviço
- Valor do contrato (em BRL) e condições de pagamento
- Data de início e duração
- Cláusulas especiais ou requisitos adicionais

Faça perguntas naturais, uma ou duas por vez.
Quando tiver TODAS as informações obrigatórias, responda SOMENTE com JSON válido neste formato exato:
{"complete": true, "data": {"client_name": "...", "cpf_cnpj": "...", "service_description": "...", "contract_value": 0.00, "payment_terms": "...", "start_date": "YYYY-MM-DD", "duration_months": 0, "special_clauses": "..."}}

Importante:
- Não inclua texto antes ou depois do JSON
- Garanta JSON válido e bem formatado
- Só marque complete=true quando todos os campos obrigatórios estiverem preenchidos"""

        try:
            async def runner(provider: str) -> str:
                if provider == "anthropic":
                    logger.info("Sending conversation to Claude with %s messages", len(conversation_history))
                    return await self._anthropic_collect(
                        conversation_history=conversation_history,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                    )

                if provider == "gemini":
                    return await self._gemini_generate(
                        message="Continue a conversa e peça a próxima informação que falta para o contrato.",
                        system_prompt=system_prompt,
                        conversation_history=conversation_history,
                        max_tokens=max_tokens,
                    )

                if provider == "openai":
                    return await self._openai_generate(
                        message="Continue a conversa e peça a próxima informação que falta para o contrato.",
                        system_prompt=system_prompt,
                        conversation_history=conversation_history,
                        max_tokens=max_tokens,
                    )

                raise ValueError(f"Unsupported provider: {provider}")

            assistant_message = await self._run_with_fallback("collect_contract_data", runner)
            logger.debug("AI response: %s", assistant_message[:100])

            if '"complete": true' in assistant_message or '"complete":true' in assistant_message:
                try:
                    data = json.loads(assistant_message)
                    if not isinstance(data, dict) or "complete" not in data or "data" not in data:
                        logger.warning("AI returned malformed completion response")
                        return {
                            "complete": False,
                            "message": "Perfeito. Agora, por favor, informe os dados que ainda faltam.",
                        }

                    logger.info("Contract data collection complete")
                    return data
                except json.JSONDecodeError as exc:
                    logger.error("Failed to parse AI JSON response: %s", exc)
                    return {
                        "complete": False,
                        "message": "Pode confirmar novamente as informações para eu concluir o contrato?",
                    }

            return {
                "complete": False,
                "message": assistant_message,
            }

        except RateLimitError as exc:
            logger.error("Claude API rate limit exceeded: %s", exc)
            raise
        except APIConnectionError as exc:
            logger.error("Failed to connect to Claude API: %s", exc)
            raise
        except APIError as exc:
            logger.error("Claude API error: %s", exc)
            raise
        except Exception as exc:
            logger.error("Unexpected error in collect_contract_data: %s", exc)
            raise ValueError(f"Unexpected error in contract data collection: {exc}")

    async def send_message(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Send a single message to AI provider and return text response.
        """
        try:
            async def runner(provider: str) -> str:
                if provider == "anthropic":
                    logger.info("Sending single message to Claude")
                    return await self._anthropic_send(
                        message=message,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        conversation_history=conversation_history,
                    )

                if provider == "gemini":
                    logger.info("Sending single message to Gemini")
                    return await self._gemini_generate(
                        message=message,
                        system_prompt=system_prompt,
                        conversation_history=conversation_history,
                        max_tokens=max_tokens,
                    )

                if provider == "openai":
                    logger.info("Sending single message to OpenAI")
                    return await self._openai_generate(
                        message=message,
                        system_prompt=system_prompt,
                        conversation_history=conversation_history,
                        max_tokens=max_tokens,
                    )

                raise ValueError(f"Unsupported provider: {provider}")

            return await self._run_with_fallback("send_message", runner)

        except (RateLimitError, APIConnectionError, APIError) as exc:
            logger.error("Claude API error in send_message: %s", exc)
            raise
        except Exception as exc:
            logger.error("Unexpected error in send_message: %s", exc)
            raise ValueError(f"Unexpected error in send_message: {exc}")

    def validate_collected_data(self, data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate that all required contract fields are present and valid.
        """
        required_fields = [
            "client_name",
            "cpf_cnpj",
            "service_description",
            "contract_value",
            "payment_terms",
            "start_date",
            "duration_months",
        ]

        errors = []

        for field in required_fields:
            if field not in data or not data[field]:
                errors.append(f"Missing required field: {field}")

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
