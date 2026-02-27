"""
Conversational AI API Endpoints

This module provides FastAPI endpoints for managing conversational data collection
using Claude AI. Supports multi-turn conversations for collecting contract information
and other structured data.

Endpoints:
- POST /start - Start a new conversation
- POST /{conversation_id}/message - Send a message in a conversation
- GET /{conversation_id} - Get conversation details and history
- DELETE /{conversation_id} - Clear/delete a conversation
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
import uuid
import logging

from app.services.claude_service import ClaudeService
from app.database import get_db
from app.models.conversation import Conversation
from app.config import settings
from anthropic import APIError

logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _conversation_ttl() -> timedelta:
    ttl_hours = max(int(settings.CONVERSATION_TTL_HOURS), 1)
    return timedelta(hours=ttl_hours)


def _is_conversation_expired(conversation: Conversation, now: Optional[datetime] = None) -> bool:
    last_activity = conversation.updated_at or conversation.created_at
    if not last_activity:
        return False

    now_utc = now or _utc_now()
    cutoff = now_utc - _conversation_ttl()
    return _normalize_utc(last_activity) < cutoff


def _cleanup_expired_conversations(db: Session) -> None:
    """
    Remove conversations past TTL.

    Cleanup is best-effort and never blocks request handling if cleanup fails.
    """
    now_utc = _utc_now()
    cutoff = now_utc - _conversation_ttl()
    try:
        deleted_count = (
            db.query(Conversation)
            .filter(Conversation.updated_at < cutoff)
            .delete(synchronize_session=False)
        )
        if deleted_count > 0:
            db.commit()
            logger.info("Cleaned up %s expired conversations", deleted_count)
    except Exception:
        db.rollback()
        logger.warning("Conversation TTL cleanup failed; continuing request", exc_info=True)


def _get_active_conversation_or_404(db: Session, conversation_id: str) -> Conversation:
    _cleanup_expired_conversations(db)
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    if _is_conversation_expired(conversation):
        try:
            db.delete(conversation)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning(
                "Failed to delete expired conversation %s",
                conversation_id,
                exc_info=True,
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found or expired",
        )

    return conversation


# Pydantic schemas for request/response validation
class ConversationStartResponse(BaseModel):
    """Response when starting a new conversation"""
    conversation_id: str = Field(..., description="Unique conversation identifier")
    message: str = Field(..., description="Initial greeting from the assistant")
    created_at: datetime = Field(..., description="Conversation creation timestamp")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
            "message": "Hello! I'll help you create a service contract. To get started, could you tell me the client's full name?",
            "created_at": "2026-02-06T12:00:00Z"
        }
    })


class MessageRequest(BaseModel):
    """Request body for sending a message"""
    message: str = Field(..., min_length=1, max_length=5000, description="User message content")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "The client name is John Silva"
        }
    })


class MessageResponse(BaseModel):
    """Response after sending a message"""
    conversation_id: str = Field(..., description="Conversation identifier")
    user_message: str = Field(..., description="The user's message")
    assistant_message: str = Field(..., description="Assistant's response")
    complete: bool = Field(..., description="Whether data collection is complete")
    data: Optional[Dict[str, Any]] = Field(None, description="Collected contract data (if complete)")
    timestamp: datetime = Field(..., description="Message timestamp")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_message": "The client name is John Silva",
            "assistant_message": "Great! Now, could you provide the client's CPF or CNPJ number?",
            "complete": False,
            "data": None,
            "timestamp": "2026-02-06T12:01:00Z"
        }
    })


class ConversationResponse(BaseModel):
    """Response with full conversation details"""
    conversation_id: str = Field(..., description="Conversation identifier")
    messages: List[Dict[str, str]] = Field(..., description="Conversation message history")
    complete: bool = Field(..., description="Whether data collection is complete")
    data: Optional[Dict[str, Any]] = Field(None, description="Collected contract data (if complete)")
    created_at: datetime = Field(..., description="Conversation creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
            "messages": [
                {"role": "assistant", "content": "Hello! I'll help you create a service contract..."},
                {"role": "user", "content": "The client name is John Silva"}
            ],
            "complete": False,
            "data": None,
            "created_at": "2026-02-06T12:00:00Z",
            "updated_at": "2026-02-06T12:01:00Z"
        }
    })


@router.post("/start", response_model=ConversationStartResponse, status_code=status.HTTP_201_CREATED)
async def start_conversation(db: Session = Depends(get_db)):
    """
    Start a new conversational data collection session.

    Creates a new conversation with a unique ID and returns the initial
    greeting from the AI assistant. The assistant will guide the user
    through collecting all necessary contract information.

    Returns:
        ConversationStartResponse: Conversation ID and initial greeting

    Example:
        POST /api/conversation/start
        Response:
        {
            "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
            "message": "Hello! I'll help you create a service contract...",
            "created_at": "2026-02-06T12:00:00Z"
        }
    """
    try:
        _cleanup_expired_conversations(db)

        # Generate unique conversation ID
        conversation_id = str(uuid.uuid4())

        # Initialize Claude service
        claude_service = ClaudeService()

        # Get initial greeting from Claude
        initial_message = await claude_service.send_message(
            message=(
                "Inicie uma nova conversa de coleta de dados para contrato de prestação de serviços. "
                "Cumprimente o usuário e peça a primeira informação necessária."
            ),
            system_prompt="""Você é um assistente financeiro que coleta informações para gerar contrato de prestação de serviços.

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

Comece cumprimentando o usuário e pedindo a primeira informação (nome do cliente)."""
        )

        # Persist conversation to database
        conversation = Conversation(
            id=conversation_id,
            messages=[{"role": "assistant", "content": initial_message}],
            complete=False,
            data=None,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        logger.info(f"Started new conversation: {conversation_id}")

        return ConversationStartResponse(
            conversation_id=conversation_id,
            message=initial_message,
            created_at=conversation.created_at
        )

    except APIError as e:
        logger.error(f"Claude API error starting conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to AI service: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error starting conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start conversation"
        )


@router.post("/{conversation_id}/message", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def send_message(conversation_id: str, request: MessageRequest, db: Session = Depends(get_db)):
    """
    Send a message in an existing conversation.

    Sends the user's message to Claude and returns the assistant's response.
    The assistant will continue collecting information until all required
    data is gathered, at which point it will return complete=True with
    the structured contract data.

    Args:
        conversation_id: Unique conversation identifier from /start
        request: MessageRequest with the user's message

    Returns:
        MessageResponse: Assistant's response and completion status

    Raises:
        HTTPException 404: Conversation not found
        HTTPException 400: Conversation already complete
        HTTPException 503: AI service unavailable

    Example:
        POST /api/conversation/{conversation_id}/message
        Body: {"message": "The client name is John Silva"}
        Response:
        {
            "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
            "user_message": "The client name is John Silva",
            "assistant_message": "Great! Now, could you provide the client's CPF or CNPJ?",
            "complete": false,
            "data": null,
            "timestamp": "2026-02-06T12:01:00Z"
        }
    """
    conversation = _get_active_conversation_or_404(db, conversation_id)

    # Check if conversation is already complete
    if conversation.complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation is already complete. Start a new conversation to collect more data."
        )

    try:
        # Build updated messages list with user message
        messages = list(conversation.messages or [])
        messages.append({
            "role": "user",
            "content": request.message
        })

        # Initialize Claude service
        claude_service = ClaudeService()

        # Send conversation history to Claude for next response
        result = await claude_service.collect_contract_data(
            conversation_history=messages
        )

        # Extract response
        complete = result.get("complete", False)
        assistant_message = result.get("message", "")
        data = result.get("data", None)

        # Add assistant response to conversation history
        if not complete:
            messages.append({
                "role": "assistant",
                "content": assistant_message
            })
        else:
            completion_message = (
                "Perfeito. Já coletei todas as informações necessárias para o seu contrato."
            )
            messages.append({
                "role": "assistant",
                "content": completion_message
            })
            assistant_message = completion_message

        # Update conversation state in database
        conversation.messages = messages
        conversation.complete = complete
        conversation.data = data
        db.commit()
        db.refresh(conversation)

        logger.info(f"Message processed in conversation {conversation_id}, complete={complete}")

        return MessageResponse(
            conversation_id=conversation_id,
            user_message=request.message,
            assistant_message=assistant_message,
            complete=complete,
            data=data,
            timestamp=conversation.updated_at
        )

    except APIError as e:
        logger.error(f"Claude API error in conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to AI service: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing message in conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process message"
        )


@router.get("/{conversation_id}", response_model=ConversationResponse, status_code=status.HTTP_200_OK)
async def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """
    Get full conversation details and message history.

    Retrieves the complete conversation including all messages exchanged,
    completion status, and collected data (if available).

    Args:
        conversation_id: Unique conversation identifier

    Returns:
        ConversationResponse: Full conversation details

    Raises:
        HTTPException 404: Conversation not found

    Example:
        GET /api/conversation/{conversation_id}
        Response:
        {
            "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
            "messages": [...],
            "complete": false,
            "data": null,
            "created_at": "2026-02-06T12:00:00Z",
            "updated_at": "2026-02-06T12:01:00Z"
        }
    """
    conversation = _get_active_conversation_or_404(db, conversation_id)

    return ConversationResponse(
        conversation_id=conversation_id,
        messages=conversation.messages or [],
        complete=conversation.complete,
        data=conversation.data,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """
    Delete a conversation and its history.

    Removes the conversation from the database. This cannot be undone.
    Use this to clean up completed conversations or restart data collection.

    Args:
        conversation_id: Unique conversation identifier

    Raises:
        HTTPException 404: Conversation not found

    Example:
        DELETE /api/conversation/{conversation_id}
        Response: 204 No Content
    """
    conversation = _get_active_conversation_or_404(db, conversation_id)

    db.delete(conversation)
    db.commit()
    logger.info(f"Deleted conversation: {conversation_id}")

    # Return no content (FastAPI handles this automatically with status 204)
    return None
