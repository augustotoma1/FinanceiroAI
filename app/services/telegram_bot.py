"""
Telegram Bot Service

Provides a Telegram interface for the Financial Automation System.
Users can interact with the AI assistant, check clients, contracts,
dashboard metrics, and manage the system via Telegram messages.

Commands:
    /start - Welcome message and menu
    /novo_contrato - Start AI-guided contract creation
    /reconectar - Share Conta Azul reconnection URL
    /clientes - List recent clients
    /contratos - List recent contracts
    /templates_contrato - List available dynamic contract templates
    /preview_contrato - Generate HTML preview for a contract
    /pdf_contrato - Generate PDF for a contract
    /contratos_vencendo - Contract lifecycle (expired/expiring)
    /sync_assinaturas - Force Autentique signature reconciliation
    /dashboard - View financial metrics
    /cfo - Executive cash/risk snapshot
    /resumo_semanal - Weekly executive CFO summary on demand
    /inadimplencia - Check delinquency analysis
    /sync_financeiro - Force financial synchronization
    /operacao_dia - Daily operational executive summary
    /cobrar_email - Preview + confirm billing email dispatch
    /resumo_cobranca - Billing email operational summary (dry-run)
    /status - Check system and integration status
    /cancelar - Cancel current conversation
    /ajuda - Show help message
"""

import logging
import re
import asyncio
import hashlib
import io
from urllib.parse import urlsplit
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from app.config import settings
from app.services.claude_service import ClaudeService
from app.services.contract_generator import (
    ContractGenerator,
    ContractPDFError,
    ContractTemplateError,
    ContractValidationError,
)
from app.services.legal_knowledge_service import legal_knowledge_service
from app.database import get_db
from app.models.client import Client
from app.models.contract import Contract
from app.models.conversation import Conversation
from sqlalchemy import desc

logger = logging.getLogger(__name__)

# Store active conversations per user (chat_id -> conversation history)
active_conversations: Dict[int, list] = {}
# In-memory set of chats that have recently interacted with the bot
known_chat_ids: set[int] = set()
# Pending period selection flow per chat (e.g. "receber" or "pagar")
pending_period_requests: Dict[int, str] = {}
# Pending WhatsApp billing confirmation window per chat.
pending_whatsapp_confirmations: Dict[int, datetime] = {}
# Pending email billing confirmation window per chat.
pending_email_confirmations: Dict[int, datetime] = {}
# Pending in-chat onboarding for new client creation during /novo_contrato.
pending_client_onboarding: Dict[int, Dict[str, Any]] = {}

# Claude service instance
claude_service: Optional[ClaudeService] = None
DEFAULT_CONTRACT_TEMPLATE = "default_contract.html"


def get_claude():
    """Lazy-init Claude service."""
    global claude_service
    if claude_service is None:
        claude_service = ClaudeService()
    return claude_service


@contextmanager
def _db_session_scope():
    """Provide a DB session with guaranteed close for bot handlers."""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


def _conversation_ttl_delta() -> timedelta:
    """Return TTL configured for persisted conversation state."""
    ttl_hours = max(int(getattr(settings, "CONVERSATION_TTL_HOURS", 24)), 1)
    return timedelta(hours=ttl_hours)


def _telegram_conversation_id(chat_id: int) -> str:
    """
    Build a deterministic DB key for Telegram chat state.

    Conversation.id is varchar(36), so we hash only when necessary.
    """
    raw = f"tg-{chat_id}"
    if len(raw) <= 36:
        return raw
    digest = hashlib.sha1(str(chat_id).encode("utf-8")).hexdigest()[:33]
    return f"tg-{digest}"


def _telegram_period_flow_id(chat_id: int) -> str:
    """Build deterministic key for pending /receber|/pagar period selection."""
    raw = f"tgp-{chat_id}"
    if len(raw) <= 36:
        return raw
    digest = hashlib.sha1(f"tgp:{chat_id}".encode("utf-8")).hexdigest()[:32]
    return f"tgp-{digest}"


def _telegram_client_onboarding_id(chat_id: int) -> str:
    """Build deterministic key for pending client onboarding in Telegram."""
    raw = f"tgo-{chat_id}"
    if len(raw) <= 36:
        return raw
    digest = hashlib.sha1(f"tgo:{chat_id}".encode("utf-8")).hexdigest()[:32]
    return f"tgo-{digest}"


def _telegram_alert_chat_id(chat_id: int) -> str:
    """Build deterministic key for persistent Telegram alert chat registration."""
    raw = f"tga-{chat_id}"
    if len(raw) <= 36:
        return raw
    digest = hashlib.sha1(f"tga:{chat_id}".encode("utf-8")).hexdigest()[:32]
    return f"tga-{digest}"


def _load_persisted_alert_chat_ids() -> List[int]:
    """Load Telegram chat IDs persisted for proactive alerts."""
    db = next(get_db())
    try:
        rows = (
            db.query(Conversation.id, Conversation.data)
            .filter(Conversation.id.like("tga-%"))
            .all()
        )
        chat_ids: set[int] = set()
        for conversation_id, data in rows:
            parsed: Optional[int] = None
            if isinstance(data, dict):
                raw_chat = data.get("chat_id")
                try:
                    if raw_chat is not None:
                        parsed = int(raw_chat)
                except (TypeError, ValueError):
                    parsed = None
            if parsed is None:
                token = _as_text(conversation_id).split("tga-", 1)[-1]
                try:
                    parsed = int(token)
                except ValueError:
                    parsed = None
            if parsed is not None:
                chat_ids.add(parsed)
        return sorted(chat_ids)
    except Exception:
        db.rollback()
        logger.warning("Failed to load persisted Telegram alert chat IDs", exc_info=True)
        return []
    finally:
        db.close()


def _persist_alert_chat_id(chat_id: int) -> None:
    """Persist Telegram chat id to survive process restarts."""
    conversation_id = _telegram_alert_chat_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if record is None:
            db.add(
                Conversation(
                    id=conversation_id,
                    messages=[],
                    complete=True,
                    data={"kind": "telegram_alert_chat", "chat_id": int(chat_id)},
                )
            )
        else:
            payload = dict(record.data or {})
            payload["kind"] = "telegram_alert_chat"
            payload["chat_id"] = int(chat_id)
            record.data = payload
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to persist Telegram alert chat ID", exc_info=True)
    finally:
        db.close()


def _load_persisted_contract_history(chat_id: int) -> Optional[List[Dict[str, str]]]:
    """Load active contract flow history from DB if it exists and is not expired."""
    conversation_id = _telegram_conversation_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not record:
            return None

        if record.complete:
            db.delete(record)
            db.commit()
            return None

        now = datetime.now(timezone.utc)
        last_activity = record.updated_at or record.created_at
        if last_activity:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            if last_activity < (now - _conversation_ttl_delta()):
                db.delete(record)
                db.commit()
                return None

        messages = list(record.messages or [])
        return messages if messages else None
    except Exception:
        db.rollback()
        logger.warning("Failed to load persisted Telegram conversation state", exc_info=True)
        return None
    finally:
        db.close()


def _save_persisted_contract_history(
    chat_id: int,
    messages: List[Dict[str, str]],
    *,
    complete: bool = False,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Upsert Telegram contract flow history in DB."""
    conversation_id = _telegram_conversation_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        now = datetime.now(timezone.utc)
        if record:
            record.messages = messages
            record.complete = complete
            record.data = data
            record.updated_at = now
        else:
            record = Conversation(
                id=conversation_id,
                messages=messages,
                complete=complete,
                data=data,
            )
            db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to persist Telegram conversation state", exc_info=True)
    finally:
        db.close()


def _clear_persisted_contract_history(chat_id: int) -> None:
    """Delete persisted Telegram contract flow state."""
    conversation_id = _telegram_conversation_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if record:
            db.delete(record)
            db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to clear persisted Telegram conversation state", exc_info=True)
    finally:
        db.close()


def _load_persisted_period_flow(chat_id: int) -> Optional[str]:
    """Load pending period flow (/receber or /pagar) from DB."""
    conversation_id = _telegram_period_flow_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not record:
            return None

        now = datetime.now(timezone.utc)
        last_activity = record.updated_at or record.created_at
        if last_activity:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            if last_activity < (now - _conversation_ttl_delta()):
                db.delete(record)
                db.commit()
                return None

        flow = _as_text((record.data or {}).get("flow")).lower()
        if flow not in {"receber", "pagar"}:
            db.delete(record)
            db.commit()
            return None
        return flow
    except Exception:
        db.rollback()
        logger.warning("Failed to load persisted period flow state", exc_info=True)
        return None
    finally:
        db.close()


def _save_persisted_period_flow(chat_id: int, flow: str) -> None:
    """Upsert pending period flow selection in DB."""
    normalized_flow = _as_text(flow).lower()
    if normalized_flow not in {"receber", "pagar"}:
        return

    conversation_id = _telegram_period_flow_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        now = datetime.now(timezone.utc)
        if record:
            record.messages = []
            record.complete = False
            record.data = {"flow": normalized_flow}
            record.updated_at = now
        else:
            record = Conversation(
                id=conversation_id,
                messages=[],
                complete=False,
                data={"flow": normalized_flow},
            )
            db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to persist period flow state", exc_info=True)
    finally:
        db.close()


def _clear_persisted_period_flow(chat_id: int) -> None:
    """Delete persisted pending period flow selection."""
    conversation_id = _telegram_period_flow_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if record:
            db.delete(record)
            db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to clear persisted period flow state", exc_info=True)
    finally:
        db.close()


def _load_persisted_client_onboarding(chat_id: int) -> Optional[Dict[str, Any]]:
    """Load pending new-client onboarding state from DB."""
    conversation_id = _telegram_client_onboarding_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not record:
            return None

        now = datetime.now(timezone.utc)
        last_activity = record.updated_at or record.created_at
        if last_activity:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            if last_activity < (now - _conversation_ttl_delta()):
                db.delete(record)
                db.commit()
                return None

        data = record.data if isinstance(record.data, dict) else {}
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        step = _as_text(payload.get("step")).lower()
        if step not in {"confirm", "email", "phone"}:
            db.delete(record)
            db.commit()
            return None
        contract_data = payload.get("contract_data") if isinstance(payload.get("contract_data"), dict) else {}
        client_payload = payload.get("client_payload") if isinstance(payload.get("client_payload"), dict) else {}
        return {
            "step": step,
            "contract_data": contract_data,
            "client_payload": client_payload,
        }
    except Exception:
        db.rollback()
        logger.warning("Failed to load persisted client onboarding state", exc_info=True)
        return None
    finally:
        db.close()


def _save_persisted_client_onboarding(chat_id: int, payload: Dict[str, Any]) -> None:
    """Upsert pending client onboarding state in DB."""
    step = _as_text((payload or {}).get("step")).lower()
    if step not in {"confirm", "email", "phone"}:
        return

    safe_payload = {
        "step": step,
        "contract_data": dict((payload or {}).get("contract_data") or {}),
        "client_payload": dict((payload or {}).get("client_payload") or {}),
    }

    conversation_id = _telegram_client_onboarding_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        now = datetime.now(timezone.utc)
        if record:
            record.messages = []
            record.complete = False
            record.data = {"kind": "telegram_client_onboarding", "payload": safe_payload}
            record.updated_at = now
        else:
            record = Conversation(
                id=conversation_id,
                messages=[],
                complete=False,
                data={"kind": "telegram_client_onboarding", "payload": safe_payload},
            )
            db.add(record)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to persist client onboarding state", exc_info=True)
    finally:
        db.close()


def _clear_persisted_client_onboarding(chat_id: int) -> None:
    """Delete persisted pending client onboarding state."""
    conversation_id = _telegram_client_onboarding_id(chat_id)
    db = next(get_db())
    try:
        record = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if record:
            db.delete(record)
            db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to clear client onboarding state", exc_info=True)
    finally:
        db.close()


async def track_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture chat IDs from incoming updates for proactive notifications."""
    _ = context  # Unused by design; handler signature requires it.
    chat = update.effective_chat
    if chat and chat.id:
        chat_id = int(chat.id)
        if chat_id not in known_chat_ids:
            known_chat_ids.add(chat_id)
            _persist_alert_chat_id(chat_id)


def _is_whatsapp_phase_enabled() -> bool:
    """Return True when WhatsApp feature is enabled for the current rollout phase."""
    return bool(getattr(settings, "WHATSAPP_FEATURE_ENABLED", False))


def _parse_email_test_recipients(raw_value: Optional[str]) -> List[str]:
    raw = _as_text(raw_value)
    if not raw:
        return []
    items = raw.replace(";", ",").split(",")
    recipients: List[str] = []
    seen: set[str] = set()
    for item in items:
        email = _as_text(item).lower()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)
        recipients.append(email)
    return recipients


# ─── Command Handlers ────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    _ = context
    user = update.effective_user
    lines = [
        f"Olá, {user.first_name}! 👋",
        "",
        "Sou o assistente financeiro da AISATEC.",
        "Posso te ajudar com:",
        "",
        "📝 /novo_contrato — Criar contrato com IA",
        "👥 /clientes — Ver clientes",
        "📄 /contratos — Ver contratos",
        "🧩 /templates_contrato — Ver templates dinâmicos",
        "👁️ /preview_contrato — Gerar prévia HTML do contrato",
        "📎 /pdf_contrato — Gerar PDF do contrato",
        "⏳ /contratos_vencendo — Contratos próximos ao vencimento",
        "✍️ /sync_assinaturas — Atualizar assinaturas Autentique",
        "🔄 /sincronizar — Puxar clientes do Conta Azul",
        "",
        "🔐 /reconectar — Reconectar Conta Azul",
        "",
        "🔁 /sync_financeiro — Sincronizar receber/pagar",
        "",
    ]

    if settings.EMAIL_BILLING_ENABLED:
        lines.extend(
            [
                "📧 /cobrar_email — Prévia + confirmação de cobrança por e-mail",
                "📨 /resumo_cobranca — Resumo operacional de cobrança por e-mail",
                "",
            ]
        )

    if _is_whatsapp_phase_enabled():
        lines.extend(
            [
                "📲 /cobrar_whatsapp — Prévia de cobrança WhatsApp",
                "⛔ /wa_bloqueados — Ver números bloqueados no WAHA",
                "🔓 /wa_desbloquear — Desbloquear número(s) WAHA",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "📴 WhatsApp: adiado para fase final (apenas simulado nesta etapa)",
                "",
            ]
        )

    lines.extend(
        [
            "💰 /receber — Contas a receber",
            "💸 /pagar — Contas a pagar",
            "🏦 /saldos — Saldos das contas",
            "⚠️ /inadimplencia — Parcelas atrasadas",
            "",
            "📊 /dashboard — Métricas financeiras",
            "🧭 /cfo — Painel executivo CFO",
            "🧩 /operacao_dia — Operação diária consolidada",
            "📆 /resumo_semanal — Resumo semanal CFO",
            "🔗 /status — Status das integrações",
            "❓ /ajuda — Ajuda completa",
            "",
            "Ou simplesmente me envie uma mensagem e eu converso com você!",
        ]
    )

    await update.message.reply_text("\n".join(lines))


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ajuda command."""
    _ = context
    email_help = "• Cobrança e-mail — desativada nesta etapa\n"
    if settings.EMAIL_BILLING_ENABLED:
        email_help = (
            "• /cobrar\\_email — Prévia obrigatória + confirmação de envio por e-mail\n"
            "• /resumo\\_cobranca — Resumo operacional de cobrança \\(simulação\\)\n"
        )
    whatsapp_help = (
        "• WhatsApp — adiado para fase final \\(teste simulado nesta etapa\\)\n"
    )
    if _is_whatsapp_phase_enabled():
        whatsapp_help = (
            "• /cobrar\\_whatsapp — Prévia obrigatória + confirmação de envio\n"
            "• /wa\\_bloqueados — Lista números bloqueados automaticamente\n"
            "• /wa\\_desbloquear — Remove bloqueio por número ou todos\n"
        )

    await update.message.reply_text(
        "📖 *Guia Completo*\n\n"
        "*Criar Contratos:*\n"
        "Use /novo\\_contrato e eu vou te guiar passo a passo "
        "para coletar todos os dados necessários: cliente, serviço, "
        "valor, prazo e cláusulas. No final, gero o PDF automaticamente.\n\n"
        "*Consultas:*\n"
        "• /clientes — Lista os últimos 10 clientes\n"
        "• /contratos — Lista os últimos 10 contratos\n"
        "• /templates\\_contrato — Lista templates dinâmicos disponíveis\n"
        "• /preview\\_contrato <id> [template] — Gera prévia HTML\n"
        "• /pdf\\_contrato <id> [template] — Gera PDF do contrato\n"
        "• /contratos\\_vencendo — Contratos vencidos e próximos do vencimento\n"
        "• /sync\\_assinaturas — Reconciliar assinaturas com Autentique\n"
        "• /dashboard — KPIs: receita, inadimplência, contratos\n\n"
        "*Financeiro \\(Conta Azul\\):*\n"
        f"{email_help}"
        f"{whatsapp_help}"
        "• /receber — Contas a receber \\(pede período ou aceite: /receber 30d\\)\n"
        "• /pagar — Contas a pagar \\(ex.: /pagar 2026-02-01 2026-02-28\\)\n"
        "• /saldos — Saldos bancários e caixa\n"
        "• /inadimplencia — Parcelas em atraso por cliente\n"
        "• /sincronizar — Atualizar clientes do Conta Azul\n\n"
        "*Executivo:*\n"
        "• /cfo — Risco de caixa, projeção 15 dias e concentração de carteira\n"
        "• /operacao\\_dia — Visão diária consolidada de operação e saúde do sistema\n"
        "• /resumo\\_semanal — Resumo executivo semanal sob demanda\n"
        "• /sync\\_financeiro — Sync financeiro \\(aceita período: 7d, mes, intervalo\\)\n\n"
        "*Integrações:*\n"
        "• Conta Azul — Clientes, financeiro, contas\n"
        "• Autentique — Assinatura eletrônica de contratos\n"
        "• Use /status para verificar conexões\n\n"
        "*Reautorização Conta Azul:*\n"
        "• /reconectar — Envia link de reconexão OAuth\n\n"
        "*Conversa Livre:*\n"
        "Fora de um fluxo de contrato, você pode me enviar qualquer "
        "pergunta sobre finanças, contratos ou o sistema.",
        parse_mode="Markdown"
    )


async def cmd_novo_contrato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new contract creation conversation."""
    chat_id = update.effective_chat.id
    pending_client_onboarding.pop(chat_id, None)
    _clear_persisted_client_onboarding(chat_id)
    active_conversations[chat_id] = []
    _save_persisted_contract_history(chat_id, [])

    await update.message.reply_text(
        "📝 *Novo Contrato*\n\n"
        "Vamos criar um contrato! Vou te fazer algumas perguntas para "
        "coletar todos os dados necessários.\n\n"
        "Pode começar me dizendo: para qual cliente é o contrato?\n\n"
        "_Use /cancelar para desistir a qualquer momento._",
        parse_mode="Markdown"
    )

    # Send initial message to Claude to start the flow
    try:
        service = get_claude()
        initial_history = [
            {"role": "user", "content": "Quero criar um novo contrato de prestação de serviço."}
        ]
        result = await service.collect_contract_data(initial_history)
        active_conversations[chat_id] = initial_history + [
            {"role": "assistant", "content": result["message"]}
        ]
        _save_persisted_contract_history(chat_id, active_conversations[chat_id])
        await update.message.reply_text(result["message"])
    except Exception as e:
        logger.error(f"Error starting contract conversation: {e}")
        await update.message.reply_text(
            "⚠️ Erro ao iniciar conversa com a IA. Tente novamente em instantes."
        )
        active_conversations.pop(chat_id, None)
        _clear_persisted_contract_history(chat_id)


def _build_conta_azul_reconnect_url(redirect_uri: str) -> str:
    """Build authorize URL using redirect URI host/path context safely."""
    default_path = "/api/auth/conta-azul/authorize"
    raw_uri = _as_text(redirect_uri)
    if not raw_uri:
        return default_path

    parsed = urlsplit(raw_uri)
    if not parsed.scheme or not parsed.netloc:
        # Fallback for malformed/non-absolute values.
        marker = "/api/auth/conta-azul/callback"
        if marker in raw_uri:
            return f"{raw_uri.split(marker, 1)[0]}{default_path}"
        return default_path

    origin = f"{parsed.scheme}://{parsed.netloc}"
    callback_marker = "/api/auth/conta-azul/callback"
    if callback_marker in parsed.path:
        prefix = parsed.path.split(callback_marker, 1)[0]
        return f"{origin}{prefix}{default_path}"

    return f"{origin}{default_path}"


async def cmd_reconectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send Conta Azul OAuth reconnection URL."""
    _ = context  # Signature compatibility
    reconnect_url = _build_conta_azul_reconnect_url(settings.CONTA_AZUL_REDIRECT_URI)
    await update.message.reply_text(
        "Reconexão Conta Azul\n\n"
        "1. Abra o link abaixo no navegador:\n"
        f"{reconnect_url}\n\n"
        "2. Faça login no Conta Azul e autorize o app.\n"
        "3. Volte ao bot e rode /status para validar."
    )


async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current conversation."""
    chat_id = update.effective_chat.id
    had_flow = False
    if chat_id in active_conversations:
        del active_conversations[chat_id]
        had_flow = True
    _clear_persisted_contract_history(chat_id)
    if chat_id in pending_client_onboarding:
        pending_client_onboarding.pop(chat_id, None)
        _clear_persisted_client_onboarding(chat_id)
        had_flow = True
    _clear_persisted_period_flow(chat_id)
    if chat_id in pending_period_requests:
        del pending_period_requests[chat_id]
        had_flow = True
    if had_flow:
        await update.message.reply_text("❌ Conversa cancelada. Use /novo_contrato para recomeçar.")
    else:
        await update.message.reply_text("Nenhuma conversa ativa para cancelar.")


async def cmd_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List recent clients."""
    try:
        with _db_session_scope() as db:
            clients = db.query(Client).order_by(desc(Client.created_at)).limit(10).all()

        if not clients:
            await update.message.reply_text("Nenhum cliente cadastrado ainda.")
            return

        lines = ["👥 *Últimos Clientes:*\n"]
        for i, c in enumerate(clients, 1):
            name = c.name or "Sem nome"
            doc = c.cpf_cnpj or "Sem doc"
            email = c.email or ""
            line = f"{i}. *{name}*\n   📋 {doc}"
            if email:
                line += f" | ✉️ {email}"
            lines.append(line)

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error listing clients: {e}")
        await update.message.reply_text("⚠️ Erro ao buscar clientes. Verifique o banco de dados.")


async def cmd_contratos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List recent contracts."""
    try:
        with _db_session_scope() as db:
            contracts = db.query(Contract).order_by(desc(Contract.created_at)).limit(10).all()

        if not contracts:
            await update.message.reply_text("Nenhum contrato cadastrado ainda.")
            return

        status_emoji = {
            "draft": "📝",
            "pending_signature": "✍️",
            "signed": "✅",
            "active": "🟢",
            "cancelled": "❌",
            "expired": "⏰",
        }

        lines = ["📄 *Últimos Contratos:*\n"]
        for i, c in enumerate(contracts, 1):
            emoji = status_emoji.get(c.status, "📄")
            value = f"R$ {c.contract_value:,.2f}" if c.contract_value else "N/A"
            lines.append(
                f"{i}. {emoji} *{c.service_description[:40]}*\n"
                f"   💰 {value} | Status: {c.status}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error listing contracts: {e}")
        await update.message.reply_text("⚠️ Erro ao buscar contratos.")


def _normalize_contract_template_name(raw_template: Optional[str]) -> str:
    """Validate and normalize contract template file name."""
    template_name = (_as_text(raw_template) or DEFAULT_CONTRACT_TEMPLATE).strip()
    if not template_name:
        template_name = DEFAULT_CONTRACT_TEMPLATE

    if "/" in template_name or "\\" in template_name or ".." in template_name:
        raise ValueError("Template inválido. Use apenas o nome do arquivo HTML.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", template_name):
        raise ValueError("Template inválido. Caracteres permitidos: letras, números, ponto, hífen e underscore.")
    if not template_name.lower().endswith((".html", ".htm")):
        raise ValueError("Template inválido. Use um arquivo .html.")

    return template_name


def _parse_contract_template_args(args: List[str], command_name: str) -> tuple[int, str]:
    """Parse `<contract_id> [template_name]` from command args."""
    if not args:
        raise ValueError(f"Uso: /{command_name} <id_contrato> [template.html]")

    contract_token = _as_text(args[0]).strip()
    if not contract_token:
        raise ValueError(f"Uso: /{command_name} <id_contrato> [template.html]")

    try:
        contract_id = int(contract_token)
    except ValueError:
        raise ValueError("ID do contrato inválido. Use um número inteiro.")

    template_token = args[1] if len(args) > 1 else DEFAULT_CONTRACT_TEMPLATE
    template_name = _normalize_contract_template_name(template_token)
    return contract_id, template_name


def _build_contract_template_payload(contract: Contract, client: Client) -> Dict[str, Any]:
    """Map DB models to template payload fields expected by ContractGenerator."""
    return {
        "client_name": client.name,
        "cpf_cnpj": client.cpf_cnpj,
        "service_description": contract.service_description,
        "contract_value": float(contract.contract_value or 0),
        "payment_terms": contract.payment_terms,
        "start_date": contract.start_date.isoformat() if contract.start_date else None,
        "duration_months": contract.duration_months,
        "special_clauses": contract.notes or "",
    }


def _get_contract_with_client(db, contract_id: int) -> tuple[Optional[Contract], Optional[Client]]:
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        return None, None
    client = db.query(Client).filter(Client.id == contract.client_id).first()
    return contract, client


async def cmd_templates_contrato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available Jinja2 contract templates."""
    _ = context
    try:
        generator = ContractGenerator()
        templates = generator.list_available_templates()
        if not templates:
            await update.message.reply_text("Nenhum template de contrato encontrado.")
            return

        lines = ["📚 Templates de contrato disponíveis:\n"]
        for idx, template in enumerate(templates, 1):
            marker = " (padrão)" if template == DEFAULT_CONTRACT_TEMPLATE else ""
            lines.append(f"{idx}. {template}{marker}")
        lines.append("\nUso:")
        lines.append("• /preview_contrato <id_contrato> [template.html]")
        lines.append("• /pdf_contrato <id_contrato> [template.html]")

        await update.message.reply_text("\n".join(lines))
    except Exception as exc:
        logger.error("Error listing contract templates: %s", exc, exc_info=True)
        await update.message.reply_text("⚠️ Erro ao listar templates de contrato.")


async def cmd_preview_contrato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send HTML preview for a contract template."""
    try:
        contract_id, template_name = _parse_contract_template_args(context.args, "preview_contrato")
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    try:
        with _db_session_scope() as db:
            contract, client = _get_contract_with_client(db, contract_id)
            if not contract:
                await update.message.reply_text(f"⚠️ Contrato {contract_id} não encontrado.")
                return
            if not client:
                await update.message.reply_text(
                    f"⚠️ Cliente do contrato {contract_id} não encontrado no sistema."
                )
                return

            payload = _build_contract_template_payload(contract, client)
            contract_number = _as_text(contract.contract_number) or f"CTR-{contract.id}"

        await update.message.reply_chat_action("upload_document")
        generator = ContractGenerator()
        html = await generator.generate_contract_html(
            contract_data=payload,
            contract_id=contract_number,
            template_name=template_name,
        )

        doc_bytes = io.BytesIO(html.encode("utf-8"))
        doc_name = f"{contract_number}-preview.html"
        await update.message.reply_document(
            document=doc_bytes,
            filename=doc_name,
            caption=f"Prévia HTML do contrato {contract_number} (template: {template_name})",
        )
    except (ContractValidationError, ContractTemplateError) as exc:
        await update.message.reply_text(f"⚠️ Não foi possível gerar prévia: {str(exc)[:200]}")
    except Exception as exc:
        logger.error("Error generating contract HTML preview: %s", exc, exc_info=True)
        await update.message.reply_text("⚠️ Erro ao gerar prévia do contrato.")


async def cmd_pdf_contrato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send contract PDF from selected template."""
    try:
        contract_id, template_name = _parse_contract_template_args(context.args, "pdf_contrato")
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    try:
        with _db_session_scope() as db:
            contract, client = _get_contract_with_client(db, contract_id)
            if not contract:
                await update.message.reply_text(f"⚠️ Contrato {contract_id} não encontrado.")
                return
            if not client:
                await update.message.reply_text(
                    f"⚠️ Cliente do contrato {contract_id} não encontrado no sistema."
                )
                return

            payload = _build_contract_template_payload(contract, client)
            contract_number = _as_text(contract.contract_number) or f"CTR-{contract.id}"

        await update.message.reply_chat_action("upload_document")
        generator = ContractGenerator()
        pdf_bytes = await generator.generate_contract_pdf(
            contract_data=payload,
            contract_id=contract_number,
            template_name=template_name,
        )

        await update.message.reply_document(
            document=io.BytesIO(pdf_bytes),
            filename=f"{contract_number}.pdf",
            caption=f"PDF do contrato {contract_number} (template: {template_name})",
        )
    except (ContractValidationError, ContractTemplateError, ContractPDFError) as exc:
        await update.message.reply_text(f"⚠️ Não foi possível gerar PDF: {str(exc)[:200]}")
    except Exception as exc:
        logger.error("Error generating contract PDF: %s", exc, exc_info=True)
        await update.message.reply_text("⚠️ Erro ao gerar PDF do contrato.")


def _build_contract_lifecycle_lines(
    snapshot: Dict[str, Any],
    *,
    updated_count: int = 0,
    limit: int = 8,
) -> List[str]:
    """Build human-readable contract lifecycle summary lines."""
    window_days = int(snapshot.get("window_days") or 30)
    overdue = list(snapshot.get("overdue") or [])
    expiring = list(snapshot.get("expiring_soon") or [])
    missing = list(snapshot.get("missing_end_date") or [])

    lines = ["⏳ Ciclo de Vida de Contratos"]
    lines.append(f"Janela: próximos {window_days} dias")
    lines.append(
        f"Monitorados: {int(snapshot.get('monitored_total') or 0)} | "
        f"Vencidos: {len(overdue)} | "
        f"A vencer: {len(expiring)} | "
        f"Sem data fim: {len(missing)}"
    )
    if updated_count > 0:
        lines.append(f"Status atualizado para expirado: {updated_count}")

    if not overdue and not expiring and not missing:
        lines.append("\n✅ Sem alertas de vencimento no momento.")
        return lines

    if overdue:
        lines.append("\n🔴 Vencidos:")
        for idx, item in enumerate(overdue[:max(1, limit)], 1):
            dias = abs(int(item.get("days_to_end") or 0))
            lines.append(
                f"{idx}. {item.get('contract_number')} | {item.get('client_name')[:24]} | "
                f"{dias} dia(s) atrasado(s) | fim: {item.get('end_date')}"
            )

    if expiring:
        lines.append("\n🟡 A vencer:")
        for idx, item in enumerate(expiring[:max(1, limit)], 1):
            dias = int(item.get("days_to_end") or 0)
            lines.append(
                f"{idx}. {item.get('contract_number')} | {item.get('client_name')[:24]} | "
                f"{dias} dia(s) | fim: {item.get('end_date')}"
            )

    if missing:
        lines.append("\n⚠️ Sem data fim:")
        for idx, item in enumerate(missing[:5], 1):
            lines.append(
                f"{idx}. {item.get('contract_number')} | {item.get('client_name')[:24]} | status: {item.get('status')}"
            )

    return lines


async def cmd_contratos_vencendo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show contract lifecycle summary for expired/expiring contracts."""
    window_days = int(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_DAYS", 30))
    if context.args:
        token = _as_text(context.args[0])
        if token:
            try:
                parsed = int(token)
                if parsed < 1 or parsed > 365:
                    raise ValueError
                window_days = parsed
            except ValueError:
                await update.message.reply_text(
                    "⚠️ Período inválido. Use: /contratos_vencendo 30"
                )
                return

    try:
        from app.services.contract_lifecycle_service import (
            build_contract_lifecycle_snapshot,
            mark_expired_contracts,
        )

        with _db_session_scope() as db:
            maintenance = mark_expired_contracts(db)
            snapshot = build_contract_lifecycle_snapshot(db, days_ahead=window_days)

        lines = _build_contract_lifecycle_lines(
            snapshot,
            updated_count=int(maintenance.get("updated_count") or 0),
        )
        await update.message.reply_text("\n".join(lines))
    except Exception as exc:
        logger.error("Error in contract lifecycle summary: %s", exc, exc_info=True)
        await update.message.reply_text(f"⚠️ Erro ao gerar ciclo de vida: {str(exc)[:200]}")


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show dashboard metrics."""
    try:
        with _db_session_scope() as db:
            total_clients = db.query(Client).count()
            total_contracts = db.query(Contract).count()

            active_contracts = db.query(Contract).filter(
                Contract.status.in_(["active", "signed"])
            ).count()

            pending_sig = db.query(Contract).filter(
                Contract.status == "pending_signature"
            ).count()

            from sqlalchemy import func
            total_value = db.query(func.sum(Contract.contract_value)).filter(
                Contract.status.in_(["active", "signed"])
            ).scalar() or 0

        await update.message.reply_text(
            "📊 *Dashboard Financeiro*\n\n"
            f"👥 Clientes: *{total_clients}*\n"
            f"📄 Contratos total: *{total_contracts}*\n"
            f"🟢 Ativos/Assinados: *{active_contracts}*\n"
            f"✍️ Aguardando assinatura: *{pending_sig}*\n"
            f"💰 Valor total ativo: *R$ {total_value:,.2f}*",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        await update.message.reply_text("⚠️ Erro ao carregar métricas.")


async def cmd_inadimplencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check delinquency analysis."""
    try:
        from app.services.delinquency_analyzer import DelinquencyAnalyzer
        analyzer = DelinquencyAnalyzer()
        with _db_session_scope() as db:
            results = analyzer.analyze_all_clients(db, min_risk_level="medium")

        if not results:
            await update.message.reply_text(
                "✅ Nenhum cliente com risco médio ou alto de inadimplência!"
            )
            return

        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        lines = ["⚠️ *Análise de Inadimplência:*\n"]
        for r in results[:10]:
            emoji = risk_emoji.get(r.get("risk_level", ""), "⚪")
            lines.append(
                f"{emoji} *{r.get('client_name', 'N/A')}*\n"
                f"   Score: {r.get('risk_score', 0)}/100 | "
                f"Atrasado: R$ {r.get('total_overdue', 0):,.2f}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in delinquency analysis: {e}")
        await update.message.reply_text("⚠️ Erro na análise de inadimplência.")


async def cmd_sincronizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually sync clients from Conta Azul."""
    await update.message.reply_text("🔄 Sincronizando clientes do Conta Azul... Aguarde.")

    try:
        from app.background.sync_clients import sync_clients_job
        result = await sync_clients_job()

        if result["success"]:
            await update.message.reply_text(
                "✅ *Sincronização concluída!*\n\n"
                f"📥 Total sincronizados: *{result['synced_count']}*\n"
                f"🆕 Novos clientes: *{result['created_count']}*\n"
                f"🔄 Atualizados: *{result['updated_count']}*\n"
                f"⚠️ Erros: *{result['error_count']}*\n"
                f"⏱ Tempo: {result['duration_seconds']:.1f}s",
                parse_mode="Markdown"
            )
        elif result.get("partial_success"):
            await update.message.reply_text(
                "⚠️ *Sincronização parcial de clientes*\n\n"
                f"📥 Total sincronizados: *{result.get('synced_count', 0)}*\n"
                f"🆕 Novos clientes: *{result.get('created_count', 0)}*\n"
                f"🔄 Atualizados: *{result.get('updated_count', 0)}*\n"
                f"⚠️ Erros: *{result.get('error_count', 0)}*\n"
                f"🔎 Primeiro erro: {(result.get('errors') or ['N/A'])[0]}\n"
                f"⏱ Tempo: {float(result.get('duration_seconds', 0.0)):.1f}s",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⚠️ Sincronização concluída com problemas.\n"
                f"Erros: {result.get('error_count', 0)}\n"
                f"Detalhe: {(result.get('errors') or ['N/A'])[0]}"
            )

    except Exception as e:
        logger.error(f"Error in manual sync: {e}")
        error_msg = str(e).lower()

        if "invalid_grant" in error_msg or "reautorize" in error_msg:
            await update.message.reply_text(
                "🔴 Integração com Conta Azul expirou.\n\n"
                "O token de refresh foi revogado/expirado.\n"
                "É necessário reconectar:\n"
                "1️⃣ Acesse GET /api/auth/conta-azul/authorize\n"
                "2️⃣ Faça login no Conta Azul e autorize\n"
                "3️⃣ Depois use /status para confirmar conexão"
            )
        else:
            await update.message.reply_text(
                f"❌ Erro na sincronização: {str(e)[:200]}\n\n"
                "Verifique se o Conta Azul está conectado com /status"
            )


async def cmd_sync_financeiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually force financial synchronization job with optional period."""
    args_text = " ".join(context.args).strip() if context.args else ""

    if not args_text:
        await _request_period_selection(update, "sync_financeiro")
        return

    try:
        data_de, data_ate, label = _parse_period_input(args_text)
    except ValueError as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        await _request_period_selection(update, "sync_financeiro")
        return

    await _send_sync_financeiro_report(update, data_de, data_ate, label)


async def cmd_sync_assinaturas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually force Autentique signature synchronization job."""
    args_text = " ".join(context.args).strip() if context.args else ""
    max_contracts: Optional[int] = None

    if args_text:
        try:
            max_contracts = max(1, int(args_text))
        except ValueError:
            await update.message.reply_text(
                "⚠️ Parâmetro inválido. Use /sync_assinaturas ou /sync_assinaturas 50"
            )
            return

    scope_label = (
        f"até {max_contracts} contrato(s)"
        if max_contracts is not None
        else f"até {settings.AUTENTIQUE_SIGNATURE_SYNC_MAX_CONTRACTS} contrato(s)"
    )
    await update.message.reply_text(
        f"🔄 Sincronizando assinaturas no Autentique ({scope_label})..."
    )

    try:
        from app.background.sync_signatures import sync_signatures_job

        result = await sync_signatures_job(max_contracts=max_contracts)
        if result.get("success"):
            await update.message.reply_text(
                "✅ *Sync de assinaturas concluída!*\n\n"
                f"📄 Contratos processados: *{result.get('processed_contracts', 0)}*\n"
                f"🆕 Assinaturas criadas: *{result.get('created_signatures', 0)}*\n"
                f"🔄 Assinaturas atualizadas: *{result.get('updated_signatures', 0)}*\n"
                f"📌 Contratos atualizados: *{result.get('updated_contracts', 0)}*\n"
                f"⚠️ Erros: *{result.get('error_count', 0)}*\n"
                f"⏱ Tempo: {float(result.get('duration_seconds', 0.0)):.1f}s",
                parse_mode="Markdown",
            )
            return

        if result.get("partial_success"):
            await update.message.reply_text(
                "⚠️ *Sync de assinaturas parcial*\n\n"
                f"📄 Contratos processados: *{result.get('processed_contracts', 0)}*\n"
                f"🆕 Assinaturas criadas: *{result.get('created_signatures', 0)}*\n"
                f"🔄 Assinaturas atualizadas: *{result.get('updated_signatures', 0)}*\n"
                f"📌 Contratos atualizados: *{result.get('updated_contracts', 0)}*\n"
                f"⚠️ Erros: *{result.get('error_count', 0)}*\n"
                f"🔎 Primeiro erro: {(result.get('errors') or ['N/A'])[0]}",
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(
            "⚠️ Sync de assinaturas finalizada com erro.\n"
            f"Detalhe: {(result.get('errors') or [result.get('reason', 'N/A')])[0]}"
        )
    except Exception as e:
        logger.error("Error running Autentique signature sync: %s", e, exc_info=True)
        await update.message.reply_text(
            f"❌ Erro na sync de assinaturas: {str(e)[:220]}"
        )


def _build_whatsapp_preview_lines(result: Dict[str, Any], *, limit: int = 12) -> List[str]:
    """Format a human-readable preview list for WhatsApp billing targets."""
    targets = list(result.get("targets_preview") or [])
    if not targets:
        return ["Nenhum cliente elegível para cobrança no momento."]

    level_emoji = {1: "🟡", 2: "🟠", 3: "🔴"}
    lines = ["📋 *Prévia de cobrança (sem envio):*"]
    for idx, target in enumerate(targets[:max(1, limit)], 1):
        level = int(target.get("level") or 1)
        emoji = level_emoji.get(level, "⚪")
        client_name = _as_text(target.get("client_name")) or "Cliente"
        phone = _as_text(target.get("to_phone")) or "sem telefone"
        total_amount = float(target.get("total_amount") or 0.0)
        items_count = int(target.get("items_count") or 0)
        lines.append(
            f"{idx}. {emoji} {client_name[:30]} | {phone} | "
            f"{_format_brl(total_amount)} | {items_count} título(s)"
        )

    hidden = len(targets) - max(1, limit)
    if hidden > 0:
        lines.append(f"... e mais {hidden} destinatário(s).")
    return lines


def _build_email_preview_lines(result: Dict[str, Any], *, limit: int = 12) -> List[str]:
    """Format a human-readable preview list for billing email targets."""
    targets = list(result.get("targets_preview") or [])
    if not targets:
        return ["Nenhum cliente elegível para cobrança no momento."]

    level_emoji = {1: "🟡", 2: "🟠", 3: "🔴"}
    lines = ["📋 *Prévia de cobrança por e-mail (sem envio):*"]
    for idx, target in enumerate(targets[:max(1, limit)], 1):
        level = int(target.get("level") or 1)
        emoji = level_emoji.get(level, "⚪")
        client_name = _as_text(target.get("client_name")) or "Cliente"
        to_email = _as_text(target.get("to_email")) or "sem e-mail"
        total_amount = float(target.get("total_amount") or 0.0)
        items_count = int(target.get("items_count") or 0)
        first_due = _as_text(target.get("first_due_date"))
        due_hint = f" | 1o venc: {first_due}" if first_due else ""
        lines.append(
            f"{idx}. {emoji} {client_name[:30]} | `{to_email}` | "
            f"{_format_brl(total_amount)} | {items_count} título(s){due_hint}"
        )

    hidden = len(targets) - max(1, limit)
    if hidden > 0:
        lines.append(f"... e mais {hidden} destinatário(s).")
    return lines


def _whatsapp_confirmation_active(chat_id: int, *, ttl_minutes: int = 15) -> bool:
    """Return True when a pending WhatsApp send confirmation is still valid."""
    created_at = pending_whatsapp_confirmations.get(chat_id)
    if not created_at:
        return False
    expires_at = created_at + timedelta(minutes=max(ttl_minutes, 1))
    if datetime.now(timezone.utc) > expires_at:
        pending_whatsapp_confirmations.pop(chat_id, None)
        return False
    return True


def _email_confirmation_active(chat_id: int, *, ttl_minutes: int = 15) -> bool:
    """Return True when a pending email send confirmation is still valid."""
    created_at = pending_email_confirmations.get(chat_id)
    if not created_at:
        return False
    expires_at = created_at + timedelta(minutes=max(ttl_minutes, 1))
    if datetime.now(timezone.utc) > expires_at:
        pending_email_confirmations.pop(chat_id, None)
        return False
    return True


async def cmd_cobrar_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Run billing email campaign with mandatory preview + confirmation.
    """
    if not settings.EMAIL_BILLING_ENABLED:
        await update.message.reply_text(
            "📭 Cobrança por e-mail está desativada.\n"
            "Ative EMAIL_BILLING_ENABLED=true para usar este comando."
        )
        return

    chat_id = getattr(update.effective_chat, "id", 0)
    args = [str(arg).strip().lower() for arg in (context.args or []) if str(arg).strip()]
    wants_send = any(token in {"confirmar", "confirmo", "confirm", "enviar", "real", "send"} for token in args)
    wants_cancel = any(token in {"cancelar", "cancel", "parar"} for token in args)

    if wants_cancel:
        pending_email_confirmations.pop(chat_id, None)
        await update.message.reply_text("❌ Envio de cobrança por e-mail cancelado.")
        return

    logger.info(
        "cmd_cobrar_email triggered chat_id=%s args=%s wants_send=%s provider=%s",
        chat_id,
        args,
        wants_send,
        getattr(settings, "EMAIL_BILLING_PROVIDER", "log"),
    )

    try:
        from app.services.email_billing_service import run_billing_email_campaign

        if wants_send:
            if not bool(getattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", False)):
                pending_email_confirmations.pop(chat_id, None)
                await update.message.reply_text(
                    "🛑 Envio real por e-mail está em *standby*.\n"
                    "Nesta fase o sistema permite apenas prévia/simulação.\n\n"
                    "Use `/cobrar_email` para revisar a carteira e `/resumo_cobranca` para auditoria operacional.",
                    parse_mode="Markdown",
                )
                return
            if not _email_confirmation_active(chat_id):
                await update.message.reply_text(
                    "⚠️ Envio bloqueado por segurança.\n"
                    "Primeiro rode /cobrar_email para gerar a prévia e confirmar os destinatários.\n"
                    "Depois use /cobrar_email confirmar."
                )
                return
            await update.message.reply_text("📧 Enviando cobrança por e-mail (confirmação recebida)...")
            result = await run_billing_email_campaign(dry_run=False)
            pending_email_confirmations.pop(chat_id, None)
        else:
            await update.message.reply_text("📋 Gerando prévia de cobrança por e-mail...")
            result = await run_billing_email_campaign(dry_run=True)

        logger.info(
            "cmd_cobrar_email result success=%s sent=%s dry=%s failed=%s eligible_clients=%s",
            result.get("success"),
            result.get("emails_sent"),
            result.get("emails_dry_run"),
            result.get("emails_failed"),
            result.get("eligible_clients"),
        )

        if wants_send:
            if result.get("success"):
                lines = [
                    "✅ *Cobrança por e-mail concluída*",
                    "",
                    f"📤 Enviadas: *{result.get('emails_sent', 0)}*",
                    f"🧪 Simulação: *{result.get('emails_dry_run', 0)}*",
                    f"⚠️ Falhas: *{result.get('emails_failed', 0)}*",
                    f"👥 Clientes elegíveis: *{result.get('eligible_clients', 0)}*",
                    f"🧾 Registros elegíveis: *{result.get('eligible_records', 0)}*",
                    f"📭 Sem e-mail: *{result.get('skipped_missing_email', 0)}*",
                    f"Nível 1: {result.get('level_counts', {}).get('1', 0)} | "
                    f"Nível 2: {result.get('level_counts', {}).get('2', 0)} | "
                    f"Nível 3: {result.get('level_counts', {}).get('3', 0)}",
                    f"⏱ Tempo: {float(result.get('duration_seconds', 0.0)):.1f}s",
                ]
                if result.get("test_mode"):
                    targets = [f"`{_as_text(email)}`" for email in (result.get("test_recipients") or [])]
                    if targets:
                        lines.append("🧪 Destinos de teste: " + ", ".join(targets[:3]) + ("..." if len(targets) > 3 else ""))
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            else:
                await update.message.reply_text(
                    "⚠️ Cobrança por e-mail concluída com erros.\n"
                    f"Falhas: {result.get('emails_failed', 0)}\n"
                    f"Detalhe: {(result.get('errors') or ['N/A'])[0]}"
                )
            return

        preview_lines = _build_email_preview_lines(result)
        await update.message.reply_text("\n".join(preview_lines), parse_mode="Markdown")

        if int(result.get("eligible_clients") or 0) <= 0:
            pending_email_confirmations.pop(chat_id, None)
            await update.message.reply_text(
                "Nenhum destinatário elegível para envio real nesta prévia."
            )
            return

        pending_email_confirmations[chat_id] = datetime.now(timezone.utc)
        lines = [
            "✅ Prévia pronta e *nenhum e-mail foi enviado*.",
            "Se estiver correto, confirme em até 15 minutos com:",
            "`/cobrar_email confirmar`",
            "",
            "Para cancelar:",
            "`/cobrar_email cancelar`",
        ]
        if result.get("test_mode"):
            targets = [f"`{_as_text(email)}`" for email in (result.get("test_recipients") or [])]
            if targets:
                lines.extend(
                    [
                        "",
                        "🧪 Modo teste ativo. Destinos reais serão bloqueados e enviados apenas para:",
                        ", ".join(targets[:3]) + ("..." if len(targets) > 3 else ""),
                    ]
                )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        pending_email_confirmations.pop(chat_id, None)
        logger.error("Error in manual email billing campaign: %s", exc, exc_info=True)
        await update.message.reply_text(f"❌ Erro na cobrança por e-mail: {str(exc)[:220]}")


async def cmd_resumo_cobranca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate billing email summary in dry-run mode without sending messages."""
    _ = context
    if not settings.EMAIL_BILLING_ENABLED:
        await update.message.reply_text(
            "📭 Cobrança por e-mail está desativada nesta etapa."
        )
        return

    await update.message.reply_text("Montando resumo de cobrança por e-mail...")
    try:
        from app.services.email_billing_service import run_billing_email_campaign

        result = await run_billing_email_campaign(dry_run=True)
        lines = _build_email_billing_alert_lines(result)
        lines[0] = "Resumo Cobrança E-mail (sob demanda)"
        await update.message.reply_text("\n".join(lines))
    except Exception as exc:
        logger.error("Error generating billing email summary: %s", exc, exc_info=True)
        await update.message.reply_text(f"❌ Erro ao gerar resumo de cobrança: {str(exc)[:220]}")


async def cmd_cobrar_whatsapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Run WhatsApp billing campaign with mandatory preview + confirmation.
    """
    if not _is_whatsapp_phase_enabled():
        await update.message.reply_text(
            "📴 WhatsApp está adiado para a fase final.\n"
            "Nesta etapa de testes usamos somente fluxo simulado sem disparo."
        )
        return

    chat_id = getattr(update.effective_chat, "id", 0)
    args = [str(arg).strip().lower() for arg in (context.args or []) if str(arg).strip()]
    wants_send = any(token in {"confirmar", "confirmo", "confirm", "enviar", "real", "send"} for token in args)
    wants_cancel = any(token in {"cancelar", "cancel", "parar"} for token in args)

    if wants_cancel:
        pending_whatsapp_confirmations.pop(chat_id, None)
        await update.message.reply_text("❌ Envio de cobrança WhatsApp cancelado.")
        return

    logger.info(
        "cmd_cobrar_whatsapp triggered chat_id=%s args=%s wants_send=%s provider=%s",
        chat_id,
        args,
        wants_send,
        getattr(settings, "WHATSAPP_BILLING_PROVIDER", "log"),
    )

    try:
        from app.services.whatsapp_billing_service import run_whatsapp_billing_campaign

        if wants_send:
            if not _whatsapp_confirmation_active(chat_id):
                await update.message.reply_text(
                    "⚠️ Envio bloqueado por segurança.\n"
                    "Primeiro rode /cobrar_whatsapp para gerar a prévia e confirmar os números.\n"
                    "Depois use /cobrar_whatsapp confirmar."
                )
                return
            await update.message.reply_text("📲 Enviando cobrança WhatsApp (confirmação recebida)...")
            result = await run_whatsapp_billing_campaign(dry_run=False)
            pending_whatsapp_confirmations.pop(chat_id, None)
        else:
            await update.message.reply_text("📋 Gerando prévia de cobrança WhatsApp...")
            result = await run_whatsapp_billing_campaign(dry_run=True)

        logger.info(
            "cmd_cobrar_whatsapp result success=%s sent=%s dry=%s failed=%s eligible_clients=%s",
            result.get("success"),
            result.get("messages_sent"),
            result.get("messages_dry_run"),
            result.get("messages_failed"),
            result.get("eligible_clients"),
        )

        if wants_send:
            if result.get("success"):
                await update.message.reply_text(
                    "✅ *Cobrança WhatsApp concluída*\n\n"
                    f"📤 Enviadas: *{result.get('messages_sent', 0)}*\n"
                    f"⚠️ Falhas: *{result.get('messages_failed', 0)}*\n"
                    f"👥 Clientes elegíveis: *{result.get('eligible_clients', 0)}*\n"
                    f"🧾 Registros elegíveis: *{result.get('eligible_records', 0)}*\n"
                    f"📵 Sem telefone: *{result.get('skipped_missing_phone', 0)}*\n"
                    f"⛔ Bloqueados (LID): *{result.get('skipped_blocked_phone', 0)}*\n"
                    f"Nível 1: {result.get('level_counts', {}).get('1', 0)} | "
                    f"Nível 2: {result.get('level_counts', {}).get('2', 0)} | "
                    f"Nível 3: {result.get('level_counts', {}).get('3', 0)}\n"
                    f"⏱ Tempo: {float(result.get('duration_seconds', 0.0)):.1f}s",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    "⚠️ Cobrança WhatsApp concluída com erros.\n"
                    f"Falhas: {result.get('messages_failed', 0)}\n"
                    f"No LID: {result.get('error_type_counts', {}).get('no_lid', 0)} | "
                    f"Rate limit: {result.get('error_type_counts', {}).get('rate_limit', 0)}\n"
                    f"Detalhe: {(result.get('errors') or ['N/A'])[0]}\n\n"
                    "Dica: números sem WhatsApp ativo podem falhar com erro de LID."
                )
            return

        preview_lines = _build_whatsapp_preview_lines(result)
        await update.message.reply_text("\n".join(preview_lines), parse_mode="Markdown")
        if result.get("blocked_targets_preview"):
            blocked = result.get("blocked_targets_preview") or []
            lines = ["⛔ *Bloqueados automaticamente (LID):*"]
            for idx, item in enumerate(blocked[:8], 1):
                lines.append(
                    f"{idx}. {_as_text(item.get('client_name'))[:28]} | {_as_text(item.get('to_phone'))}"
                )
            hidden = len(blocked) - 8
            if hidden > 0:
                lines.append(f"... e mais {hidden} bloqueado(s).")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        if int(result.get("eligible_clients") or 0) <= 0:
            pending_whatsapp_confirmations.pop(chat_id, None)
            await update.message.reply_text(
                "Nenhum destinatário elegível para envio real nesta prévia."
            )
            return

        pending_whatsapp_confirmations[chat_id] = datetime.now(timezone.utc)
        await update.message.reply_text(
            "✅ Prévia pronta e *nenhuma mensagem foi enviada*.\n"
            "Se estiver correto, confirme em até 15 minutos com:\n"
            "`/cobrar_whatsapp confirmar`\n\n"
            "Para cancelar:\n"
            "`/cobrar_whatsapp cancelar`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        pending_whatsapp_confirmations.pop(chat_id, None)
        logger.error("Error in manual WhatsApp billing campaign: %s", exc, exc_info=True)
        await update.message.reply_text(f"❌ Erro na cobrança WhatsApp: {str(exc)[:200]}")


async def cmd_whatsapp_bloqueados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List WhatsApp numbers currently blocked due to hard WAHA failures."""
    if not _is_whatsapp_phase_enabled():
        await update.message.reply_text(
            "📴 WhatsApp está adiado para a fase final nesta etapa de testes."
        )
        return

    _ = context
    try:
        from app.services.whatsapp_billing_service import list_blocked_whatsapp_targets

        blocked = list_blocked_whatsapp_targets(limit=50)
        if not blocked:
            await update.message.reply_text("✅ Nenhum número bloqueado no momento.")
            return

        lines = ["⛔ *Números bloqueados para cobrança WhatsApp:*"]
        for idx, item in enumerate(blocked[:20], 1):
            reason = _as_text(item.get("reason")) or "unknown"
            blocked_until = _as_text(item.get("blocked_until"))[:19] or "sem prazo"
            lines.append(
                f"{idx}. {_as_text(item.get('phone'))} | motivo: {reason} | até: {blocked_until}"
            )
        if len(blocked) > 20:
            lines.append(f"... e mais {len(blocked) - 20} número(s).")
        lines.append("")
        lines.append("Para desbloquear: `/wa_desbloquear 5565999990001`")
        lines.append("Para limpar todos: `/wa_desbloquear todos`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        logger.error("Error listing blocked WhatsApp targets: %s", exc, exc_info=True)
        await update.message.reply_text(f"❌ Erro ao listar bloqueados: {str(exc)[:200]}")


async def cmd_whatsapp_desbloquear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear WhatsApp blocked targets by number or all."""
    if not _is_whatsapp_phase_enabled():
        await update.message.reply_text(
            "📴 WhatsApp está adiado para a fase final nesta etapa de testes."
        )
        return

    args = [str(arg).strip() for arg in (context.args or []) if str(arg).strip()]
    if not args:
        await update.message.reply_text(
            "Informe um número para desbloquear (ex.: /wa_desbloquear 5565999990001)\n"
            "Ou use `/wa_desbloquear todos` para limpar todos.",
            parse_mode="Markdown",
        )
        return

    try:
        from app.services.whatsapp_billing_service import clear_blocked_whatsapp_targets

        token = _as_text(args[0]).lower()
        if token in {"todos", "all"}:
            deleted = clear_blocked_whatsapp_targets(clear_all=True)
        else:
            deleted = clear_blocked_whatsapp_targets(phones=args)

        await update.message.reply_text(f"✅ Desbloqueio concluído. Registros removidos: {deleted}")
    except Exception as exc:
        logger.error("Error clearing blocked WhatsApp targets: %s", exc, exc_info=True)
        await update.message.reply_text(f"❌ Erro ao desbloquear: {str(exc)[:200]}")


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler for unsupported Telegram commands."""
    _ = context
    tip = "Use /ajuda para ver os comandos disponíveis."
    if settings.EMAIL_BILLING_ENABLED:
        tip += "\nDica: para cobrança por e-mail use /cobrar_email."
    if _is_whatsapp_phase_enabled():
        tip += "\nDica: para cobrança use /cobrar_whatsapp."
    await update.message.reply_text(
        "⚠️ Comando não reconhecido.\n"
        f"{tip}"
    )


async def _send_sync_financeiro_report(
    update: Update,
    data_de: str,
    data_ate: str,
    label: str,
):
    """Run financial sync for a selected period and report status."""
    try:
        from app.background.sync_financial import sync_financial_job

        await update.message.reply_text(
            f"🔄 Sincronizando financeiro (receber/pagar) — período: {label}..."
        )

        result = await sync_financial_job(
            data_vencimento_de=data_de,
            data_vencimento_ate=data_ate,
        )
        if result.get("success"):
            source_totals = result.get("source_totals", {})
            await update.message.reply_text(
                "✅ *Sync financeiro concluído!*\n\n"
                f"📥 Registros sincronizados: *{result.get('synced_count', 0)}*\n"
                f"🆕 Novos: *{result.get('created_count', 0)}*\n"
                f"🔄 Atualizados: *{result.get('updated_count', 0)}*\n"
                f"⚠️ Erros: *{result.get('error_count', 0)}*\n"
                f"💰 Receber lidos: *{source_totals.get('receber', 0)}*\n"
                f"💸 Pagar lidos: *{source_totals.get('pagar', 0)}*\n"
                f"📅 Período: *{data_de} a {data_ate}*\n"
                f"⏱ Tempo: {float(result.get('duration_seconds', 0.0)):.1f}s",
                parse_mode="Markdown",
            )
        elif result.get("partial_success"):
            source_totals = result.get("source_totals", {})
            await update.message.reply_text(
                "⚠️ *Sync financeiro parcial*\n\n"
                f"📥 Registros sincronizados: *{result.get('synced_count', 0)}*\n"
                f"⚠️ Erros: *{result.get('error_count', 0)}*\n"
                f"💰 Receber lidos: *{source_totals.get('receber', 0)}*\n"
                f"💸 Pagar lidos: *{source_totals.get('pagar', 0)}*\n"
                f"📅 Período: *{data_de} a {data_ate}*\n"
                f"🔎 Primeiro erro: {(result.get('errors') or ['N/A'])[0]}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "⚠️ Sync financeiro terminou com falhas.\n"
                f"Período: {data_de} a {data_ate}\n"
                f"Erros: {result.get('error_count', 0)}\n"
                f"Detalhe: {(result.get('errors') or ['N/A'])[0]}"
            )

    except Exception as e:
        logger.error(f"Error in manual financial sync: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Erro no sync financeiro: {str(e)[:200]}")


async def _get_conta_azul_token():
    """Helper to get a valid Conta Azul access token.

    Returns:
        Tuple of (access_token, error_message).
        On success: (token_string, None)
        On failure: (None, user-facing error message)
    """
    from app.models.integration_token import IntegrationToken
    from app.services.conta_azul_service import (
        ContaAzulService,
        ContaAzulInvalidGrantError,
    )
    from datetime import datetime, timezone

    with _db_session_scope() as db:
        token_record = db.query(IntegrationToken).filter_by(service="conta_azul").first()

        if not token_record:
            return None, "Conta Azul não conectado. Use /status para verificar."

        if token_record.is_expired():
            try:
                service = ContaAzulService()
                new_token_data = await service.refresh_access_token(
                    refresh_token=token_record.refresh_token
                )
                token_record.access_token = new_token_data["access_token"]
                token_record.refresh_token = new_token_data.get("refresh_token", token_record.refresh_token)
                from datetime import timedelta
                token_record.expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=new_token_data.get("expires_in", 3600)
                )
                db.commit()

            except ContaAzulInvalidGrantError:
                # Refresh token permanently invalid — full re-authorization needed
                logger.error("invalid_grant detected in _get_conta_azul_token — OAuth re-auth required")
                return None, (
                    "🔴 Integração com Conta Azul expirou (invalid_grant).\n\n"
                    "O token de refresh foi revogado ou expirou.\n"
                    "Para reconectar, use /reconectar.\n"
                    "Depois execute /status para confirmar."
                )

            except Exception as e:
                return None, f"Erro ao renovar token: {str(e)[:100]}"

        return token_record.access_token, None


def _get_conta_azul_token_expiry_info() -> Optional[Dict[str, Any]]:
    """Return Conta Azul token expiry metadata for proactive alerts."""
    from app.models.integration_token import IntegrationToken

    with _db_session_scope() as db:
        token_record = db.query(IntegrationToken).filter_by(service="conta_azul").first()
        if not token_record or not token_record.expires_at:
            return None

        expires_at = token_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)

        seconds_to_expiry = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        return {
            "expires_at": expires_at,
            "seconds_to_expiry": seconds_to_expiry,
        }


def _format_expiry_eta(seconds_to_expiry: int) -> str:
    """Human-friendly ETA text for token expiration windows."""
    if seconds_to_expiry <= 0:
        return "expirado"
    if seconds_to_expiry < 3600:
        return f"expira em {max(seconds_to_expiry // 60, 1)} min"
    if seconds_to_expiry < 86400:
        return f"expira em {seconds_to_expiry // 3600}h"
    return f"expira em {seconds_to_expiry // 86400}d"


def _esc(text):
    """Escape Telegram MarkdownV2 special characters."""
    if not text:
        return ""
    text = str(text)
    for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, '\\' + ch)
    return text


def _format_brl(value):
    """Format a number as Brazilian Real currency string."""
    try:
        v = float(value or 0)
        formatted = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    except (ValueError, TypeError):
        return "R$ 0,00"


def _as_text(value) -> str:
    """Best-effort conversion of heterogeneous API fields to readable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("nome", "name", "razao_social", "descricao", "description", "titulo", "title"):
            candidate = value.get(key)
            if candidate:
                return _as_text(candidate)
        # Fallback: concatenate scalar values only
        parts = [_as_text(v) for v in value.values() if isinstance(v, (str, int, float, bool))]
        return " ".join(p for p in parts if p).strip()
    if isinstance(value, (list, tuple, set)):
        parts = [_as_text(v) for v in value]
        return " ".join(p for p in parts if p).strip()
    return str(value).strip()


def _truncate_text(value, max_len: int) -> str:
    """Trim text to fit DB column limits safely."""
    return _as_text(value)[:max_len]


def _normalize_client_tax_id(value) -> str:
    """Normalize CPF/CNPJ to numeric text within DB max length."""
    digits = re.sub(r"\D", "", _as_text(value))
    if digits:
        return digits[:20]
    return _truncate_text(value, 20)


def _is_affirmative_answer(value) -> bool:
    """Return True for affirmative short replies in onboarding flows."""
    normalized = _as_text(value).lower()
    return normalized in {"sim", "s", "yes", "y", "ok", "confirmo", "confirmar"}


def _is_negative_answer(value) -> bool:
    """Return True for negative short replies in onboarding flows."""
    normalized = _as_text(value).lower()
    return normalized in {"nao", "não", "n", "no", "cancelar"}


def _is_skip_answer(value) -> bool:
    """Return True when user chooses to skip an optional field."""
    normalized = _as_text(value).lower()
    return normalized in {"pular", "skip", "nao", "não", "-", "nenhum", "n/a", "na"}


def _is_valid_email(value) -> bool:
    """Simple email sanity check for optional onboarding capture."""
    email = _as_text(value).lower()
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


def _build_contract_payload(contract_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize collected contract data into DB-ready values."""
    start_date = _parse_date(contract_data.get("start_date"))
    if start_date is None:
        start_date = datetime.now(timezone.utc).date()

    duration = 0
    raw_duration = contract_data.get("duration_months")
    try:
        duration = int(float(raw_duration))
    except (TypeError, ValueError):
        duration = 0
    duration = max(duration, 0)

    return {
        "client_name": _truncate_text(contract_data.get("client_name"), 255) or "Cliente sem nome",
        "cpf_cnpj": _normalize_client_tax_id(contract_data.get("cpf_cnpj")),
        "service_description": _as_text(contract_data.get("service_description")) or "Serviço não informado",
        "contract_value": _to_float(contract_data.get("contract_value")),
        "payment_terms": _as_text(contract_data.get("payment_terms")) or "Condição de pagamento não informada",
        "start_date": start_date,
        "duration_months": duration,
        "special_clauses": _as_text(contract_data.get("special_clauses")),
    }


def _save_contract_draft(db, client_id: int, contract_data: Dict[str, Any]) -> str:
    """Persist contract draft and return generated contract number."""
    payload = _build_contract_payload(contract_data)
    import uuid

    contract_number = (
        f"TG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-"
        f"{uuid.uuid4().hex[:6].upper()}"
    )
    new_contract = Contract(
        client_id=client_id,
        contract_number=contract_number,
        service_description=payload["service_description"],
        contract_value=float(payload["contract_value"]),
        payment_terms=payload["payment_terms"],
        start_date=payload["start_date"],
        duration_months=payload["duration_months"],
        notes=payload["special_clauses"] or None,
        status="draft",
    )
    db.add(new_contract)
    db.commit()
    return contract_number


def _build_client_onboarding_state(contract_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build onboarding state from collected contract data."""
    payload = _build_contract_payload(contract_data)
    start_date = payload.get("start_date")
    contract_payload = dict(payload)
    if hasattr(start_date, "isoformat"):
        contract_payload["start_date"] = start_date.isoformat()
    return {
        "step": "confirm",
        "contract_data": contract_payload,
        "client_payload": {
            "name": payload["client_name"],
            "cpf_cnpj": payload["cpf_cnpj"],
            "email": "",
            "phone": "",
        },
    }


def _short_label(primary, fallback="", max_len: int = 25) -> str:
    """Return a short, printable label from mixed input types."""
    text = _as_text(primary) or _as_text(fallback) or "N/A"
    return text[:max_len]


def _short_date(value) -> str:
    """Render date-like values safely for chat output."""
    text = _as_text(value)
    return text[:10] if text else "--"


def _to_float(value) -> float:
    """Robust numeric coercion for Conta Azul monetary fields."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _as_text(value)
    if not text:
        return 0.0
    # Handle Brazilian formats like "1.234,56"
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


_BALANCE_KEYS = (
    "saldo_atual",
    "saldo",
    "valor",
    "balance",
    "saldoAtual",
    "saldo_disponivel",
    "saldoDisponivel",
)
_BALANCE_KEYS_LOWER = {key.lower() for key in _BALANCE_KEYS}


def _has_balance_field(payload: Any) -> bool:
    """Return True when payload contains a recognized balance field."""
    if not isinstance(payload, dict):
        return False
    if any(key in payload for key in _BALANCE_KEYS):
        return True
    if any(token in str(key).lower() for key in payload.keys() for token in ("saldo", "balance")):
        return True
    nested = payload.get("saldo")
    if isinstance(nested, dict):
        return any(key in nested for key in _BALANCE_KEYS)
    return False


def _iter_balance_candidates(payload: Any):
    """Yield numeric-looking values from saldo/balance-like keys recursively."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_l = str(key).lower()
            is_balance_key = (
                key_l in _BALANCE_KEYS_LOWER
                or "saldo" in key_l
                or "balance" in key_l
            )
            if is_balance_key and not isinstance(value, (dict, list, tuple, set)):
                yield value
            yield from _iter_balance_candidates(value)
    elif isinstance(payload, (list, tuple, set)):
        for item in payload:
            yield from _iter_balance_candidates(item)


def _extract_balance_value(payload: Any) -> float:
    """Extract numeric balance from heterogeneous Conta Azul payloads."""
    if isinstance(payload, dict):
        for key in _BALANCE_KEYS:
            if key in payload and payload.get(key) is not None:
                return _to_float(payload.get(key))
        nested = payload.get("saldo")
        if isinstance(nested, dict):
            for key in _BALANCE_KEYS:
                if key in nested and nested.get(key) is not None:
                    return _to_float(nested.get(key))
        for candidate in _iter_balance_candidates(payload):
            value = _to_float(candidate)
            # Keep first non-zero candidate. If all are zero, caller still receives 0.0.
            if value != 0.0:
                return value
        return 0.0
    return _to_float(payload)


async def _resolve_conta_saldo(service, access_token: str, conta: Dict[str, Any]) -> float:
    """Resolve account balance preferring /saldo-atual endpoint when available."""
    conta_id = conta.get("id")
    if conta_id:
        for attempt in range(3):
            try:
                saldo_data = await service.get_saldo_conta(access_token, str(conta_id))
                if _has_balance_field(saldo_data):
                    return _extract_balance_value(saldo_data)
                logger.debug(
                    "Saldo endpoint without recognized fields for conta_id=%s keys=%s",
                    conta_id,
                    list(saldo_data.keys()) if isinstance(saldo_data, dict) else type(saldo_data).__name__,
                )
                break
            except Exception as exc:
                # Conta Azul enforces spike arrest (429). Retry with short backoff.
                msg = _as_text(exc).lower()
                if ("429" in msg or "spike" in msg) and attempt < 2:
                    await asyncio.sleep(0.35 * (attempt + 1))
                    continue
                break
    return _extract_balance_value(conta)


def _default_due_date_range(days_back: int = 180, days_forward: int = 180):
    """Build a default due-date range for Conta Azul financial search endpoints."""
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=days_back)).isoformat()
    end = (today + timedelta(days=days_forward)).isoformat()
    return start, end


def _period_prompt_text(flow: str) -> str:
    """Build period-selection instructions for /receber and /pagar."""
    if flow == "receber":
        alvo = "contas a receber"
    elif flow == "pagar":
        alvo = "contas a pagar"
    elif flow == "sync_financeiro":
        alvo = "sincronizacao financeira"
    else:
        alvo = "contas a receber"
    return (
        f"Período para {alvo}.\n"
        "Informe uma opção:\n"
        "- hoje\n"
        "- 7d\n"
        "- 30d\n"
        "- 90d\n"
        "- mes\n"
        "- mes_passado\n"
        "- aberto (12 meses passados e 12 futuros)\n"
        "Ou informe um intervalo customizado: 2026-02-01 2026-02-28"
    )


def _parse_user_date_token(token: str):
    """Parse user date token in supported formats."""
    from datetime import datetime

    token = _as_text(token)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data invalida: {token}")


def _parse_period_input(raw_text: str):
    """Parse period text into due-date range (start, end, label)."""
    from datetime import datetime, timedelta, timezone

    raw = _as_text(raw_text).lower().replace("mês", "mes")
    if not raw:
        raise ValueError("Informe um periodo valido.")

    today = datetime.now(timezone.utc).date()

    def month_bounds(reference_date):
        first_day = reference_date.replace(day=1)
        next_month = (first_day + timedelta(days=32)).replace(day=1)
        last_day = next_month - timedelta(days=1)
        return first_day, last_day

    presets = {
        "hoje": (today, today, "hoje"),
        "mes": (*month_bounds(today), "mes atual"),
        "mes_atual": (*month_bounds(today), "mes atual"),
        "mes_passado": (
            month_bounds(today - timedelta(days=today.day))[0],
            month_bounds(today - timedelta(days=today.day))[1],
            "mes passado",
        ),
        "aberto": (
            today - timedelta(days=365),
            today + timedelta(days=365),
            "12 meses passados e 12 futuros",
        ),
    }

    if raw in presets:
        data_de, data_ate, label = presets[raw]
        return data_de.isoformat(), data_ate.isoformat(), label

    if raw.isdigit() or (raw.endswith("d") and raw[:-1].isdigit()):
        days = int(raw[:-1] if raw.endswith("d") else raw)
        if days <= 0 or days > 730:
            raise ValueError("Use um numero de dias entre 1 e 730.")
        data_de = today
        data_ate = today + timedelta(days=days)
        return data_de.isoformat(), data_ate.isoformat(), f"proximos {days} dias"

    date_tokens = re.findall(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", raw)
    if len(date_tokens) >= 2:
        start_date = _parse_user_date_token(date_tokens[0])
        end_date = _parse_user_date_token(date_tokens[1])
        if start_date > end_date:
            raise ValueError("Data inicial maior que a data final.")
        return start_date.isoformat(), end_date.isoformat(), f"{start_date} a {end_date}"

    if len(date_tokens) == 1:
        one_date = _parse_user_date_token(date_tokens[0])
        return one_date.isoformat(), one_date.isoformat(), one_date.isoformat()

    raise ValueError("Formato invalido. Exemplo: 7d ou 2026-02-01 2026-02-28.")


async def _request_period_selection(update: Update, flow: str):
    """Store pending flow and ask user which period should be used."""
    chat = update.effective_chat
    if chat and chat.id:
        pending_period_requests[int(chat.id)] = flow
        _save_persisted_period_flow(int(chat.id), flow)
    await update.message.reply_text(_period_prompt_text(flow))


def _parse_date(value):
    """Parse supported date formats into a date object."""
    from datetime import datetime

    text = _as_text(value)
    if not text:
        return None

    date_token = text[:10]
    try:
        return datetime.strptime(date_token, "%Y-%m-%d").date()
    except ValueError:
        pass

    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _extract_conta_payload(conta: Dict[str, Any], person_fallback_key: str = "cliente") -> Dict[str, Any]:
    """Normalize mixed Conta Azul payload fields for reporting."""
    total = _to_float(
        conta.get("valor", 0)
        or conta.get("valor_total", 0)
        or conta.get("amount", 0)
        or conta.get("total", 0)
    )
    nao_pago = _to_float(conta.get("nao_pago"))
    pago = _to_float(conta.get("pago"))
    valor_aberto = nao_pago if nao_pago > 0 else max(total - pago, 0.0)

    status_raw = _as_text(conta.get("status", "")).upper()
    status_traduzido = _as_text(conta.get("status_traduzido", "")).upper()
    status_conta = status_traduzido or status_raw

    vencimento = _as_text(conta.get("data_vencimento", "") or conta.get("due_date", "") or "")
    descricao = _as_text(
        conta.get("descricao", "")
        or conta.get("description", "")
        or conta.get("observacao", "")
        or "Sem descrição"
    )
    pessoa = conta.get("pessoa", {}) or {}
    pessoa_nome = pessoa.get("nome", "") if isinstance(pessoa, dict) else pessoa
    nome_pessoa = (
        _as_text(pessoa_nome)
        or _as_text(conta.get("nome_pessoa", ""))
        or _as_text(conta.get(person_fallback_key, ""))
    )

    return {
        "total": total,
        "nao_pago": nao_pago,
        "pago": pago,
        "valor_aberto": valor_aberto,
        "status": status_conta,
        "vencimento": vencimento,
        "descricao": descricao,
        "nome_pessoa": nome_pessoa,
    }


def _append_finance_bucket(lines: List[str], title: str, items: List[Dict[str, Any]], total: float, limit: int = 8):
    """Append one section of finance items to a Telegram message."""
    if not items:
        return
    lines.append(f"\n{title} ({len(items)}) — Total: {_format_brl(total)}")
    for i, conta in enumerate(items[:limit], 1):
        nome = _short_label(conta.get("pessoa"), conta.get("desc"))
        lines.append(
            f"  {i}. {nome} — {_format_brl(conta.get('valor'))} "
            f"(venc: {_short_date(conta.get('venc'))})"
        )


def _summarize_contas_receber(contas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify receivables into overdue, due today, due in 7 days, pending and paid."""
    from datetime import datetime, timedelta, timezone

    paid_statuses = {"QUITADO", "RECEBIDO", "PAGO", "ACQUITTED", "PAID"}
    canceled_statuses = {"CANCELADO", "CANCELED", "VOID"}

    today = datetime.now(timezone.utc).date()
    next_7 = today + timedelta(days=7)

    atrasadas: List[Dict[str, Any]] = []
    vencem_hoje: List[Dict[str, Any]] = []
    vencem_7: List[Dict[str, Any]] = []
    pendentes: List[Dict[str, Any]] = []
    quitadas: List[Dict[str, Any]] = []

    total_atrasado = 0.0
    total_hoje = 0.0
    total_7 = 0.0
    total_pendente = 0.0
    total_quitado = 0.0

    for conta in contas:
        payload = _extract_conta_payload(conta, person_fallback_key="cliente")
        item = {
            "desc": payload["descricao"],
            "valor": payload["valor_aberto"],
            "venc": payload["vencimento"],
            "pessoa": payload["nome_pessoa"],
        }

        due_date = _parse_date(payload["vencimento"])

        if payload["status"] in paid_statuses or (payload["valor_aberto"] <= 0 and payload["pago"] > 0):
            quitadas.append(conta)
            total_quitado += max(payload["pago"], payload["total"])
            continue
        if payload["status"] in canceled_statuses:
            continue

        if due_date and due_date < today:
            atrasadas.append(item)
            total_atrasado += payload["valor_aberto"]
        elif due_date and due_date == today:
            vencem_hoje.append(item)
            total_hoje += payload["valor_aberto"]
        elif due_date and due_date <= next_7:
            vencem_7.append(item)
            total_7 += payload["valor_aberto"]
        else:
            pendentes.append(item)
            total_pendente += payload["valor_aberto"]

    total_aberto = total_atrasado + total_hoje + total_7 + total_pendente
    return {
        "atrasadas": atrasadas,
        "vencem_hoje": vencem_hoje,
        "vencem_7": vencem_7,
        "pendentes": pendentes,
        "quitadas": quitadas,
        "total_atrasado": total_atrasado,
        "total_hoje": total_hoje,
        "total_7": total_7,
        "total_pendente": total_pendente,
        "total_quitado": total_quitado,
        "total_aberto": total_aberto,
    }


def _summarize_contas_pagar(contas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify payables into overdue, pending and paid buckets."""
    from datetime import datetime, timezone

    paid_statuses = {"QUITADO", "PAGO", "ACQUITTED", "PAID"}
    canceled_statuses = {"CANCELADO", "CANCELED", "VOID"}
    today = datetime.now(timezone.utc).date()

    atrasadas: List[Dict[str, Any]] = []
    pendentes: List[Dict[str, Any]] = []
    quitadas: List[Dict[str, Any]] = []

    total_atrasado = 0.0
    total_pendente = 0.0
    total_quitado = 0.0

    for conta in contas:
        payload = _extract_conta_payload(conta, person_fallback_key="fornecedor")
        due_date = _parse_date(payload["vencimento"])
        item = {
            "desc": payload["descricao"],
            "valor": payload["valor_aberto"],
            "venc": payload["vencimento"],
            "pessoa": payload["nome_pessoa"],
        }

        if payload["status"] in paid_statuses or (payload["valor_aberto"] <= 0 and payload["pago"] > 0):
            quitadas.append(conta)
            total_quitado += max(payload["pago"], payload["total"])
            continue

        if payload["status"] in canceled_statuses:
            continue

        if due_date and due_date < today:
            atrasadas.append(item)
            total_atrasado += payload["valor_aberto"]
        else:
            pendentes.append(item)
            total_pendente += payload["valor_aberto"]

    return {
        "atrasadas": atrasadas,
        "pendentes": pendentes,
        "quitadas": quitadas,
        "total_atrasado": total_atrasado,
        "total_pendente": total_pendente,
        "total_quitado": total_quitado,
        "total_aberto": total_atrasado + total_pendente,
    }


def _compute_top_receber_concentration(
    contas: List[Dict[str, Any]],
    top_n: int = 3,
) -> Dict[str, Any]:
    """Compute open receivable concentration for the largest counterparties."""
    paid_statuses = {"QUITADO", "RECEBIDO", "PAGO", "ACQUITTED", "PAID"}
    canceled_statuses = {"CANCELADO", "CANCELED", "VOID"}

    total_open = 0.0
    by_client: Dict[str, float] = {}

    for conta in contas:
        payload = _extract_conta_payload(conta, person_fallback_key="cliente")
        if payload["status"] in paid_statuses or payload["status"] in canceled_statuses:
            continue
        value_open = float(payload["valor_aberto"] or 0)
        if value_open <= 0:
            continue

        client_name = _short_label(payload["nome_pessoa"], payload["descricao"], max_len=60)
        by_client[client_name] = by_client.get(client_name, 0.0) + value_open
        total_open += value_open

    ranked = sorted(by_client.items(), key=lambda item: item[1], reverse=True)
    top_clients = ranked[:top_n]
    top_sum = sum(value for _, value in top_clients)
    top_pct = (top_sum / total_open * 100.0) if total_open > 0 else 0.0

    return {
        "total_open": total_open,
        "top_clients": top_clients,
        "top_sum": top_sum,
        "top_pct": top_pct,
    }


def _classify_cash_risk(
    saldo_total: float,
    projected_15d: float,
    payable_15d: float,
    concentration_top_pct: float = 0.0,
) -> Dict[str, str]:
    """Classify cash risk index from projected position and obligations."""
    coverage = projected_15d / payable_15d if payable_15d > 0 else 999.0

    if projected_15d < 0 or saldo_total < 0:
        return {
            "level": "alto",
            "emoji": "🔴",
            "recommendation": "Priorize cobrança imediata e postergue saídas não críticas.",
        }

    if coverage < 0.5:
        return {
            "level": "medio",
            "emoji": "🟡",
            "recommendation": "Acelere recebimentos e monitore desembolsos diariamente.",
        }

    # Guardrail executivo: concentração de carteira acima de 60% nunca pode ser risco baixo.
    if concentration_top_pct > 60:
        if concentration_top_pct >= 75:
            return {
                "level": "alto",
                "emoji": "🔴",
                "recommendation": "Reduza concentração da carteira e diversifique recebíveis urgentemente.",
            }
        return {
            "level": "medio",
            "emoji": "🟡",
            "recommendation": "Concentração elevada. Priorize diversificação da carteira.",
        }

    return {
        "level": "baixo",
        "emoji": "🟢",
        "recommendation": "Manter ritmo atual e revisar concentração de carteira.",
    }


def _evaluate_cfo_targets(
    total_aberto_30d: float,
    total_atrasado_30d: float,
    top3_concentration_pct: float,
) -> Dict[str, Any]:
    """Evaluate CFO targets for delinquency and concentration."""
    meta_inadimplencia_pct = 5.0
    meta_concentracao_top3_pct = 60.0
    inadimplencia_pct = (
        (total_atrasado_30d / total_aberto_30d) * 100.0
        if total_aberto_30d > 0
        else 0.0
    )

    inadimplencia_ok = inadimplencia_pct <= meta_inadimplencia_pct
    concentracao_ok = top3_concentration_pct <= meta_concentracao_top3_pct
    score_ok = int(inadimplencia_ok) + int(concentracao_ok)

    if score_ok == 2:
        impact = "Cenário favorável para previsibilidade de caixa e execução do plano financeiro."
    elif score_ok == 1:
        impact = "Cenário estável com atenção pontual. Ajustes táticos evitam aumento de risco."
    else:
        impact = "Cenário de atenção. Priorizar redução de atraso e diversificação da carteira."

    return {
        "meta_inadimplencia_pct": meta_inadimplencia_pct,
        "meta_concentracao_top3_pct": meta_concentracao_top3_pct,
        "inadimplencia_pct": inadimplencia_pct,
        "inadimplencia_ok": inadimplencia_ok,
        "concentracao_ok": concentracao_ok,
        "impacto": impact,
    }


def _load_cash_risk_trend(history_days: int = 7) -> Optional[Dict[str, Any]]:
    """
    Load cash-risk trend from persisted snapshots when available.

    This avoids extra Conta Azul API calls inside /cfo. If no snapshot exists for
    the current day, trend is reported as unavailable.
    """
    from app.models.cash_risk_snapshot import CashRiskSnapshot
    from app.services.cash_risk_service import get_cash_risk_history, _compute_cash_risk_trend

    today = datetime.now(timezone.utc).date()

    with _db_session_scope() as db:
        current = (
            db.query(CashRiskSnapshot)
            .filter(CashRiskSnapshot.snapshot_date == today)
            .first()
        )
        if not current:
            return None

        snapshot = {
            "snapshot_date": current.snapshot_date.isoformat() if current.snapshot_date else None,
            "risk_score": float(current.risk_score or 0),
            "projected_15d": float(current.projected_15d or 0),
            "saldo_total": float(current.saldo_total or 0),
            "top3_concentration_pct": float(current.top3_concentration_pct or 0),
            "risk_level": current.risk_level or "",
        }
        history = get_cash_risk_history(db=db, days=max(2, history_days))
        return _compute_cash_risk_trend(snapshot=snapshot, history=history)


def _format_signed_brl(value: Optional[float]) -> str:
    if value is None:
        return "n/d"
    if value > 0:
        return f"+{_format_brl(value)}"
    return _format_brl(value)


def _format_signed_number(value: Optional[float], decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/d"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}{suffix}"


def _financial_sync_freshness(last_sync_time: Optional[str]) -> Optional[str]:
    """
    Build freshness note for financial synchronization recency.

    Returns a short status line or None when parsing is not possible.
    """
    if not last_sync_time:
        return "Alerta financeiro: sem histórico de sync financeira."
    try:
        dt = datetime.fromisoformat(last_sync_time.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        if age_hours > 48:
            return f"Alerta financeiro: sync defasada ({age_hours:.0f}h sem atualizar)."
        if age_hours > 24:
            return f"Atenção financeiro: última sync há {age_hours:.0f}h."
        return f"Sync financeira recente ({age_hours:.0f}h)."
    except Exception:
        return None


def _client_sync_freshness_line(
    freshness: Optional[str],
    hours_since_last_sync: Optional[float],
) -> str:
    """Build short client-sync freshness line for executive views."""
    status = (freshness or "").strip().lower()
    hours = float(hours_since_last_sync or 0.0)
    if status == "stale":
        return f"Sync clientes defasada ({hours:.1f}h sem atualizar)."
    if status == "warning":
        return f"Sync clientes em atenção ({hours:.1f}h sem atualizar)."
    if status == "fresh":
        return f"Sync clientes recente ({hours:.1f}h)."
    return "Sync clientes sem histórico."


def _format_cfo_trend_lines(
    trend: Optional[Dict[str, Any]],
    markdown: bool = True,
) -> List[str]:
    """Build CFO trend section lines from cash-risk trend payload."""
    if not trend:
        return ["\nTendência 7d: dados insuficientes (aguarde o snapshot diário)."]

    direction = str(trend.get("direction", "insufficient_data")).lower()
    strong_open = "*" if markdown else ""
    strong_close = "*" if markdown else ""

    if direction == "improving":
        headline = f"📈 Tendência 7d: {strong_open}MELHORANDO{strong_close}"
    elif direction == "worsening":
        headline = f"📉 Tendência 7d: {strong_open}PIORANDO{strong_close}"
    elif direction == "stable":
        headline = f"➡️ Tendência 7d: {strong_open}ESTÁVEL{strong_close}"
    else:
        headline = "ℹ️ Tendência 7d: dados insuficientes"

    lines = ["", headline]

    if direction in {"improving", "worsening", "stable"}:
        lines.append(
            f"- Δ Score de risco: {_format_signed_number(trend.get('risk_score_delta'), decimals=2, suffix=' pts')}"
        )
        lines.append(
            f"- Δ Projeção 15d: {_format_signed_brl(trend.get('projected_15d_delta'))}"
        )
        lines.append(
            f"- Δ Concentração Top 3: "
            f"{_format_signed_number(trend.get('top3_concentration_delta_pct'), decimals=2, suffix=' pp')}"
        )
        lines.append(
            f"- Média score 7d: {_format_signed_number(trend.get('avg_risk_score_7d'), decimals=2)}"
        )

    return lines


def _build_cfo_action_plan(
    risk_level: str,
    trend_direction: Optional[str],
    inadimplencia_ok: bool,
    concentracao_ok: bool,
) -> List[str]:
    """
    Build actionable CFO recommendations from current risk/target context.

    Returns a short ordered list focused on immediate execution.
    """
    actions: List[str] = []
    normalized_risk = (risk_level or "").strip().lower()
    normalized_trend = (trend_direction or "").strip().lower()

    if normalized_risk == "alto" or normalized_trend == "worsening":
        actions.append("Executar comitê de caixa em 24h e revisar desembolsos não críticos.")

    if not inadimplencia_ok:
        actions.append("Ativar régua de cobrança para vencidos e renegociar títulos críticos.")

    if not concentracao_ok:
        actions.append("Reduzir exposição dos 3 maiores clientes com plano de diversificação.")

    if normalized_risk == "baixo" and normalized_trend in {"improving", "stable"} and not actions:
        actions.append("Manter rotina diária e revisar metas executivas na reunião semanal.")

    if not actions:
        actions.append("Monitorar diariamente e preparar contingência para variações de caixa.")

    return actions[:3]


def _build_cfo_alert_flags(
    *,
    risk_level: str,
    projected_15d: float,
    inadimplencia_pct: float,
    meta_inadimplencia_pct: float,
    top3_concentration_pct: float,
    meta_concentracao_top3_pct: float,
    trend_direction: Optional[str],
    saldos_all_zero: bool,
) -> List[str]:
    """
    Build executive alert flags from risk, targets and data quality signals.

    Returns short imperative lines focused on what requires immediate attention.
    """
    flags: List[str] = []

    normalized_risk = (risk_level or "").strip().lower()
    normalized_trend = (trend_direction or "").strip().lower()

    if projected_15d < 0:
        flags.append(
            f"Caixa projetado 15d negativo ({_format_brl(projected_15d)})."
        )

    if normalized_risk == "alto" and projected_15d >= 0:
        flags.append("Risco de caixa classificado como ALTO.")

    if inadimplencia_pct > meta_inadimplencia_pct:
        flags.append(
            "Inadimplência acima da meta "
            f"({inadimplencia_pct:.1f}% > {meta_inadimplencia_pct:.1f}%)."
        )

    if top3_concentration_pct > meta_concentracao_top3_pct:
        flags.append(
            "Concentração Top 3 acima da meta "
            f"({top3_concentration_pct:.1f}% > {meta_concentracao_top3_pct:.1f}%)."
        )

    if normalized_trend == "worsening":
        flags.append("Tendência de risco piorando na janela de 7 dias.")

    if saldos_all_zero:
        flags.append(
            "Todas as contas financeiras retornaram saldo R$ 0,00 (validar origem dos saldos)."
        )

    return flags


async def _build_cfo_snapshot(access_token: str) -> Dict[str, Any]:
    """Build executive snapshot with cash risk, 15-day projection and concentration."""
    from datetime import datetime, timedelta, timezone
    from app.services.conta_azul_service import ContaAzulService

    today = datetime.now(timezone.utc).date()
    data_de = today.isoformat()
    data_15 = (today + timedelta(days=15)).isoformat()
    data_30 = (today + timedelta(days=30)).isoformat()

    service = ContaAzulService()

    contas_financeiras = await service.get_contas_financeiras(access_token=access_token)
    saldo_total = 0.0
    active_accounts = 0
    zero_balance_accounts = 0
    for conta in contas_financeiras:
        ativo = conta.get("ativo", True)
        if isinstance(ativo, str):
            ativo = ativo.lower() != "false"
        if not ativo:
            continue
        active_accounts += 1
        saldo_conta = await _resolve_conta_saldo(service, access_token, conta)
        saldo_total += saldo_conta
        if abs(saldo_conta) < 0.005:
            zero_balance_accounts += 1

    saldos_all_zero = active_accounts > 0 and zero_balance_accounts == active_accounts

    receber_15 = await _fetch_financial_items_paginated(
        service=service,
        access_token=access_token,
        endpoint="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
        data_vencimento_de=data_de,
        data_vencimento_ate=data_15,
        max_records=500,
        page_size=100,
    )
    pagar_15 = await _fetch_financial_items_paginated(
        service=service,
        access_token=access_token,
        endpoint="/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
        data_vencimento_de=data_de,
        data_vencimento_ate=data_15,
        max_records=500,
        page_size=100,
    )
    receber_30 = await _fetch_financial_items_paginated(
        service=service,
        access_token=access_token,
        endpoint="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
        data_vencimento_de=data_de,
        data_vencimento_ate=data_30,
        max_records=500,
        page_size=100,
    )

    receber_summary_15 = _summarize_contas_receber(receber_15)
    pagar_summary_15 = _summarize_contas_pagar(pagar_15)
    receber_summary_30 = _summarize_contas_receber(receber_30)
    concentration = _compute_top_receber_concentration(receber_30, top_n=3)

    total_receber_15 = float(receber_summary_15["total_aberto"])
    total_pagar_15 = float(pagar_summary_15["total_aberto"])
    projected_15d = saldo_total + total_receber_15 - total_pagar_15
    risk = _classify_cash_risk(
        saldo_total=saldo_total,
        projected_15d=projected_15d,
        payable_15d=total_pagar_15,
        concentration_top_pct=float(concentration["top_pct"]),
    )

    return {
        "saldo_total": saldo_total,
        "active_accounts": active_accounts,
        "zero_balance_accounts": zero_balance_accounts,
        "saldos_all_zero": saldos_all_zero,
        "receber_15": total_receber_15,
        "pagar_15": total_pagar_15,
        "projected_15d": projected_15d,
        "risk": risk,
        "concentration": concentration,
        "receber_summary_30": receber_summary_30,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _fetch_financial_items_paginated(
    service,
    access_token: str,
    endpoint: str,
    data_vencimento_de: Optional[str] = None,
    data_vencimento_ate: Optional[str] = None,
    status_filter: Optional[str] = None,
    max_records: int = 500,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch all available pages from Conta Azul financial search endpoints."""
    all_items: List[Dict[str, Any]] = []
    page = 1
    page_size = max(1, min(page_size, 100))
    max_records = max(1, max_records)

    while len(all_items) < max_records:
        request_size = min(page_size, max_records - len(all_items))
        params: Dict[str, Any] = {
            "pagina": page,
            "tamanho_pagina": request_size,
        }
        if status_filter:
            params["status"] = status_filter
        if data_vencimento_de:
            params["data_vencimento_de"] = data_vencimento_de
        if data_vencimento_ate:
            params["data_vencimento_ate"] = data_vencimento_ate

        response = await service.make_api_request(
            endpoint=endpoint,
            access_token=access_token,
            method="GET",
            params=params,
        )
        items = service._extract_items(response)
        if not items:
            break

        all_items.extend(items)
        if len(items) < request_size:
            break
        page += 1

    return all_items[:max_records]


def _get_alert_chat_ids() -> List[int]:
    """Resolve recipients for proactive alerts from env and known active chats."""
    raw = _as_text(getattr(settings, "TELEGRAM_ALERT_CHAT_IDS", ""))
    chat_ids = set(known_chat_ids)
    chat_ids.update(_load_persisted_alert_chat_ids())

    if raw:
        for chunk in raw.replace(";", ",").split(","):
            token = chunk.strip()
            if not token:
                continue
            try:
                chat_ids.add(int(token))
            except ValueError:
                logger.warning(f"Ignoring invalid TELEGRAM_ALERT_CHAT_IDS entry: {token}")

    return sorted(chat_ids)


async def _send_contas_receber_report(
    update: Update,
    data_de: str,
    data_ate: str,
    period_label: str,
):
    """Execute contas a receber report using informed date range."""
    await update.message.reply_text(f"Processando contas a receber ({period_label})...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()
        contas = await _fetch_financial_items_paginated(
            service=service,
            access_token=access_token,
            endpoint="/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
            data_vencimento_de=data_de,
            data_vencimento_ate=data_ate,
            max_records=500,
            page_size=100,
        )

        if not contas:
            await update.message.reply_text("Nenhuma conta a receber encontrada no período informado.")
            return

        summary = _summarize_contas_receber(contas)

        lines = [
            f"Relatório de Contas a Receber ({len(contas)} registros)",
            f"Período: {period_label}",
        ]
        _append_finance_bucket(
            lines,
            "ATRASADAS",
            summary["atrasadas"],
            summary["total_atrasado"],
        )
        _append_finance_bucket(
            lines,
            "VENCEM HOJE",
            summary["vencem_hoje"],
            summary["total_hoje"],
        )
        _append_finance_bucket(
            lines,
            "PRÓXIMOS 7 DIAS",
            summary["vencem_7"],
            summary["total_7"],
        )
        _append_finance_bucket(
            lines,
            "DEMAIS PENDENTES",
            summary["pendentes"],
            summary["total_pendente"],
        )

        if summary["quitadas"]:
            lines.append(
                f"\nQUITADAS: {len(summary['quitadas'])} — "
                f"Total: {_format_brl(summary['total_quitado'])}"
            )

        lines.append(f"\nResumo: {_format_brl(summary['total_aberto'])} a receber")
        if len(contas) >= 500:
            lines.append("\nObservação: exibindo até 500 registros no relatório.")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error fetching contas a receber: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao buscar contas a receber: {str(e)[:200]}")


async def _send_contas_pagar_report(
    update: Update,
    data_de: str,
    data_ate: str,
    period_label: str,
):
    """Execute contas a pagar report using informed date range."""
    await update.message.reply_text(f"Processando contas a pagar ({period_label})...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()
        contas = await _fetch_financial_items_paginated(
            service=service,
            access_token=access_token,
            endpoint="/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
            data_vencimento_de=data_de,
            data_vencimento_ate=data_ate,
            max_records=500,
            page_size=100,
        )

        if not contas:
            await update.message.reply_text("Nenhuma conta a pagar encontrada no período informado.")
            return

        pendentes = []
        atrasadas = []
        quitadas = []
        total_pendente = 0
        total_atrasado = 0
        total_quitado = 0

        from datetime import datetime, timezone
        hoje = datetime.now(timezone.utc).date()
        paid_statuses = {"QUITADO", "PAGO", "ACQUITTED", "PAID"}
        canceled_statuses = {"CANCELADO", "CANCELED", "VOID"}

        for conta in contas:
            payload = _extract_conta_payload(conta, person_fallback_key="fornecedor")
            due_date = _parse_date(payload["vencimento"])

            if payload["status"] in paid_statuses or (payload["valor_aberto"] <= 0 and payload["pago"] > 0):
                quitadas.append(conta)
                total_quitado += max(payload["pago"], payload["total"])
            elif payload["status"] in canceled_statuses:
                continue
            elif due_date and due_date < hoje:
                atrasadas.append(
                    {
                        "desc": payload["descricao"],
                        "valor": payload["valor_aberto"],
                        "venc": payload["vencimento"],
                        "pessoa": payload["nome_pessoa"],
                    }
                )
                total_atrasado += payload["valor_aberto"]
            else:
                pendentes.append(
                    {
                        "desc": payload["descricao"],
                        "valor": payload["valor_aberto"],
                        "venc": payload["vencimento"],
                        "pessoa": payload["nome_pessoa"],
                    }
                )
                total_pendente += payload["valor_aberto"]

        lines = [
            f"Relatório de Contas a Pagar ({len(contas)} registros)",
            f"Período: {period_label}",
        ]

        _append_finance_bucket(lines, "ATRASADAS", atrasadas, total_atrasado)
        _append_finance_bucket(lines, "PENDENTES", pendentes, total_pendente)

        if quitadas:
            lines.append(f"\nPAGAS: {len(quitadas)} — Total: {_format_brl(total_quitado)}")

        lines.append(f"\nResumo: {_format_brl(total_pendente + total_atrasado)} a pagar")
        if len(contas) >= 500:
            lines.append("\nObservação: exibindo até 500 registros no relatório.")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error fetching contas a pagar: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao buscar contas a pagar: {str(e)[:200]}")


async def cmd_receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask period (or use args) and list accounts receivable."""
    args_text = " ".join(context.args).strip() if context.args else ""

    if not args_text:
        await _request_period_selection(update, "receber")
        return

    try:
        data_de, data_ate, label = _parse_period_input(args_text)
    except ValueError as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        await _request_period_selection(update, "receber")
        return

    await _send_contas_receber_report(update, data_de, data_ate, label)


async def cmd_pagar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask period (or use args) and list accounts payable."""
    args_text = " ".join(context.args).strip() if context.args else ""

    if not args_text:
        await _request_period_selection(update, "pagar")
        return

    try:
        data_de, data_ate, label = _parse_period_input(args_text)
    except ValueError as exc:
        await update.message.reply_text(f"⚠️ {exc}")
        await _request_period_selection(update, "pagar")
        return

    await _send_contas_pagar_report(update, data_de, data_ate, label)


async def cmd_saldos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show financial account balances."""
    await update.message.reply_text("Processando saldos das contas financeiras...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()

        contas = await service.get_contas_financeiras(access_token=access_token)

        if not contas:
            await update.message.reply_text("Nenhuma conta financeira encontrada.")
            return

        if contas:
            logger.info(f"First conta financeira keys: {list(contas[0].keys())}")

        lines = []
        active_count = 0
        total_saldo = 0
        zero_balance_count = 0

        for conta in contas:
            nome = conta.get("nome", "") or conta.get("descricao", "") or conta.get("name", "") or "Sem nome"
            ativo = conta.get("ativo", True)

            if not ativo:
                continue

            active_count += 1
            saldo = await _resolve_conta_saldo(service, access_token, conta)
            total_saldo += saldo
            if abs(saldo) < 0.005:
                zero_balance_count += 1
            saldo_str = _format_brl(saldo)
            situacao = "Positivo" if saldo >= 0 else "Negativo"
            lines.append(f"{active_count}. {nome} — {saldo_str} ({situacao})")

        if active_count == 0:
            await update.message.reply_text("Nenhuma conta financeira ativa encontrada.")
            return

        lines.insert(0, f"Relatório de Saldos por Conta ({active_count} contas ativas)")
        lines.append(f"\nResumo: saldo total {_format_brl(total_saldo)}")
        if active_count > 0 and zero_balance_count == active_count:
            lines.append(
                "Atenção: todas as contas retornaram saldo R$ 0,00. "
                "Valide no Conta Azul se os saldos estão disponíveis nesse ambiente."
            )

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error fetching saldos: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Erro ao buscar saldos: {str(e)[:200]}")


async def cmd_cfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show executive CFO snapshot with risk index and short-term projection."""
    await update.message.reply_text("Processando painel executivo CFO...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        snapshot = await _build_cfo_snapshot(access_token)
        risk = snapshot["risk"]
        concentration = snapshot["concentration"]
        summary_30 = snapshot["receber_summary_30"]
        targets = _evaluate_cfo_targets(
            total_aberto_30d=float(summary_30["total_aberto"]),
            total_atrasado_30d=float(summary_30["total_atrasado"]),
            top3_concentration_pct=float(concentration["top_pct"]),
        )

        lines = ["*Painel Executivo CFO*"]
        lines.append(f"Risco de caixa: *{risk['level'].upper()}*")
        lines.append(f"Saldo atual: {_format_brl(snapshot['saldo_total'])}")
        lines.append(f"A receber (15d): {_format_brl(snapshot['receber_15'])}")
        lines.append(f"A pagar (15d): {_format_brl(snapshot['pagar_15'])}")
        lines.append(f"Projeção de caixa (15d): {_format_brl(snapshot['projected_15d'])}")
        lines.append(
            f"Concentração Top 3 clientes (30d): "
            f"{concentration['top_pct']:.1f}%"
        )
        if snapshot.get("saldos_all_zero"):
            lines.append(
                "Alerta: todas as contas ativas retornaram saldo R$ 0,00. "
                "Valide no Conta Azul se os saldos estão atualizados."
            )

        if concentration["top_clients"]:
            lines.append("\nTop 3 clientes em aberto:")
            for idx, (name, value) in enumerate(concentration["top_clients"], 1):
                lines.append(f"  {idx}. {name[:28]} — {_format_brl(value)}")

        lines.append("\nQualidade dos dados:")
        try:
            from app.background.sync_clients import get_sync_status as _get_sync_status

            client_sync_status = await _get_sync_status()
            lines.append(
                f"- {_client_sync_freshness_line(client_sync_status.get('sync_freshness'), client_sync_status.get('hours_since_last_sync'))}"
            )
        except Exception:
            lines.append("- Sync clientes: indisponível.")

        try:
            from app.background.sync_financial import get_financial_sync_status

            financial_sync_status = await get_financial_sync_status()
            financial_note = _financial_sync_freshness(financial_sync_status.get("last_sync_time"))
            if financial_note:
                lines.append(f"- {financial_note}")
            else:
                lines.append("- Sync financeira: indisponível.")
        except Exception:
            lines.append("- Sync financeira: indisponível.")

        status_inad = "OK" if targets["inadimplencia_ok"] else "ATENCAO"
        status_conc = "OK" if targets["concentracao_ok"] else "ATENCAO"
        lines.append("\nMetas executivas:")
        lines.append(
            f"- Inadimplência da carteira: {targets['inadimplencia_pct']:.1f}% "
            f"(meta <= {targets['meta_inadimplencia_pct']:.1f}%) - {status_inad}"
        )
        lines.append(
            f"- Concentração Top 3: {concentration['top_pct']:.1f}% "
            f"(meta <= {targets['meta_concentracao_top3_pct']:.1f}%) - {status_conc}"
        )
        trend = _load_cash_risk_trend(history_days=7)
        lines.extend(_format_cfo_trend_lines(trend))
        actions = _build_cfo_action_plan(
            risk_level=str(risk["level"]),
            trend_direction=(trend or {}).get("direction"),
            inadimplencia_ok=bool(targets["inadimplencia_ok"]),
            concentracao_ok=bool(targets["concentracao_ok"]),
        )
        alert_flags = _build_cfo_alert_flags(
            risk_level=str(risk["level"]),
            projected_15d=float(snapshot["projected_15d"]),
            inadimplencia_pct=float(targets["inadimplencia_pct"]),
            meta_inadimplencia_pct=float(targets["meta_inadimplencia_pct"]),
            top3_concentration_pct=float(concentration["top_pct"]),
            meta_concentracao_top3_pct=float(targets["meta_concentracao_top3_pct"]),
            trend_direction=(trend or {}).get("direction"),
            saldos_all_zero=bool(snapshot.get("saldos_all_zero")),
        )
        lines.append("\nAlertas executivos:")
        if alert_flags:
            for flag in alert_flags:
                lines.append(f"- {flag}")
        else:
            lines.append("- Sem alertas críticos no momento.")
        lines.append("\nPlano de ação imediato:")
        for idx, action in enumerate(actions, 1):
            lines.append(f"{idx}. {action}")
        lines.append(f"\nImpacto esperado: {targets['impacto']}")
        lines.append(f"\nRecomendação: {risk['recommendation']}")
        markdown_message = "\n".join(lines)
        try:
            await update.message.reply_text(markdown_message, parse_mode="Markdown")
        except Exception:
            # Fallback: some customer names/descriptions may contain markdown-sensitive
            # characters and break entity parsing in Telegram.
            logger.warning("Falling back to plain text for /cfo response", exc_info=True)
            plain_message = markdown_message.replace("*", "")
            await update.message.reply_text(plain_message)

    except Exception as e:
        logger.error(f"Error building CFO snapshot: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao montar painel CFO: {str(e)[:200]}")


async def cmd_inadimplencia_ca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check overdue receivables from Conta Azul."""
    await update.message.reply_text("Processando relatório de inadimplência...")

    try:
        access_token, error = await _get_conta_azul_token()
        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        from app.services.conta_azul_service import ContaAzulService
        service = ContaAzulService()
        data_de, data_ate = _default_due_date_range(days_back=365, days_forward=0)

        # Fetch receivables
        contas = await service.get_contas_receber(
            access_token=access_token,
            data_vencimento_de=data_de,
            data_vencimento_ate=data_ate,
            limit=100
        )

        if not contas:
            await update.message.reply_text("Nenhuma conta a receber encontrada.")
            return

        from datetime import datetime, timezone
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Find overdue items
        atrasados = []
        for conta in contas:
            status_conta = (conta.get("status", "") or "").upper()
            if status_conta in ("QUITADO", "PAGO", "CANCELADO", "RECEBIDO"):
                continue

            vencimento = conta.get("data_vencimento", "") or conta.get("due_date", "") or ""
            if vencimento and vencimento < hoje:
                valor = float(conta.get("valor", 0) or conta.get("valor_total", 0) or 0)
                pessoa = conta.get("pessoa", {}) or {}
                nome = pessoa.get("nome", "") or conta.get("nome_pessoa", "") or conta.get("descricao", "") or "N/A"
                descricao = conta.get("descricao", "") or ""

                # Calculate days overdue
                try:
                    venc_date = datetime.strptime(vencimento[:10], "%Y-%m-%d")
                    dias = (datetime.now() - venc_date).days
                except Exception:
                    dias = 0

                atrasados.append({
                    "nome": nome,
                    "valor": valor,
                    "vencimento": vencimento[:10],
                    "dias": dias,
                    "descricao": descricao[:40]
                })

        if not atrasados:
            await update.message.reply_text("Nenhuma parcela atrasada identificada.")
            return

        # Sort by days overdue (most overdue first)
        atrasados.sort(key=lambda x: x["dias"], reverse=True)
        total_atrasado = sum(c["valor"] for c in atrasados)

        lines = [f"Relatório de Inadimplência ({len(atrasados)} parcelas atrasadas)"]
        lines.append(f"Total em atraso: {_format_brl(total_atrasado)}\n")

        for i, c in enumerate(atrasados[:15], 1):
            nome = c['nome'][:28]
            if c['dias'] > 30:
                prioridade = "ALTA"
            elif c['dias'] > 15:
                prioridade = "MEDIA"
            else:
                prioridade = "BAIXA"
            lines.append(
                f"{i}. {nome}\n"
                f"   {prioridade} | {_format_brl(c['valor'])} | "
                f"{c['dias']} dias de atraso (venc: {c['vencimento']})"
            )

        if len(atrasados) > 15:
            lines.append(f"\n... e mais {len(atrasados) - 15} parcelas atrasadas")

        await update.message.reply_text("\n".join(lines))

    except Exception as e:
        logger.error(f"Error in inadimplencia CA: {e}", exc_info=True)
        await update.message.reply_text(f"Erro ao montar inadimplência: {str(e)[:200]}")


async def send_contract_lifecycle_alert(application: Application):
    """Send proactive contract lifecycle alert to configured Telegram chats."""
    if not bool(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_ENABLED", True)):
        return

    chat_ids = _get_alert_chat_ids()
    if not chat_ids:
        logger.info("Contract lifecycle alert skipped: TELEGRAM_ALERT_CHAT_IDS not configured")
        return

    try:
        from app.services.contract_lifecycle_service import (
            build_contract_lifecycle_snapshot,
            mark_expired_contracts,
        )

        with _db_session_scope() as db:
            maintenance = mark_expired_contracts(db)
            snapshot = build_contract_lifecycle_snapshot(
                db,
                days_ahead=int(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_DAYS", 30)),
            )

        if (
            int(snapshot.get("overdue_count") or 0) == 0
            and int(snapshot.get("expiring_soon_count") or 0) == 0
            and int(snapshot.get("missing_end_date_count") or 0) == 0
            and int(maintenance.get("updated_count") or 0) == 0
        ):
            logger.info("Contract lifecycle alert skipped: no lifecycle events in window")
            return

        lines = [
            f"Alerta Ciclo de Contratos ({datetime.now(timezone.utc).strftime('%d/%m/%Y')})"
        ]
        lines.extend(
            _build_contract_lifecycle_lines(
                snapshot,
                updated_count=int(maintenance.get("updated_count") or 0),
                limit=5,
            )[1:]
        )
        message = "\n".join(lines)
        for chat_id in chat_ids:
            try:
                await application.bot.send_message(chat_id=chat_id, text=message)
            except Exception as exc:
                logger.error(
                    "Failed to send contract lifecycle alert to chat %s: %s",
                    chat_id,
                    exc,
                    exc_info=True,
                )
    except Exception as exc:
        logger.error("Contract lifecycle alert generation failed: %s", exc, exc_info=True)


async def send_daily_cfo_alert(application: Application):
    """Send proactive daily executive alert to configured Telegram chats."""
    from datetime import datetime, timezone

    chat_ids = _get_alert_chat_ids()
    if not chat_ids:
        logger.info("Daily CFO alert skipped: TELEGRAM_ALERT_CHAT_IDS not configured")
        return

    lines = [f"Alerta Diário CFO ({datetime.now(timezone.utc).strftime('%d/%m/%Y')})"]

    access_token, error = await _get_conta_azul_token()
    if error:
        lines.append(f"\nConta Azul indisponível: {error.splitlines()[0]}")
    else:
        expiry_info = _get_conta_azul_token_expiry_info()
        if expiry_info:
            eta_text = _format_expiry_eta(int(expiry_info["seconds_to_expiry"]))
            expires_at_text = expiry_info["expires_at"].strftime("%Y-%m-%d %H:%M UTC")
            if int(expiry_info["seconds_to_expiry"]) <= 86400:
                lines.append(
                    f"\nAlerta token Conta Azul: {eta_text} "
                    f"({expires_at_text}) — programar reconexão preventiva."
                )
            else:
                lines.append(f"\nToken Conta Azul: {eta_text} ({expires_at_text})")

        try:
            snapshot = await _build_cfo_snapshot(access_token)
            summary = snapshot["receber_summary_30"]
            risk = snapshot["risk"]
            concentration = snapshot["concentration"]
            targets = _evaluate_cfo_targets(
                total_aberto_30d=float(summary["total_aberto"]),
                total_atrasado_30d=float(summary["total_atrasado"]),
                top3_concentration_pct=float(concentration["top_pct"]),
            )

            lines.append(f"\nRisco de caixa: {risk['level'].upper()}")
            lines.append(f"Saldo atual: {_format_brl(snapshot['saldo_total'])}")
            lines.append(f"Projeção de caixa (15d): {_format_brl(snapshot['projected_15d'])}")
            lines.append(f"A receber (15d): {_format_brl(snapshot['receber_15'])}")
            lines.append(f"A pagar (15d): {_format_brl(snapshot['pagar_15'])}")
            lines.append(f"Concentração Top 3 clientes (30d): {concentration['top_pct']:.1f}%")
            if snapshot.get("saldos_all_zero"):
                lines.append(
                    "Alerta: todas as contas ativas retornaram saldo R$ 0,00. "
                    "Validar saldos diretamente no Conta Azul."
                )

            lines.append("\nCarteira a receber (30d):")
            lines.append(f"- Atrasadas: {len(summary['atrasadas'])} — {_format_brl(summary['total_atrasado'])}")
            lines.append(f"- Vencem hoje: {len(summary['vencem_hoje'])} — {_format_brl(summary['total_hoje'])}")
            lines.append(f"- Próximos 7 dias: {len(summary['vencem_7'])} — {_format_brl(summary['total_7'])}")
            lines.append(f"- Demais pendentes: {len(summary['pendentes'])} — {_format_brl(summary['total_pendente'])}")
            lines.append(f"Total em aberto: {_format_brl(summary['total_aberto'])}")

            if concentration["top_clients"]:
                lines.append("\nTop 3 clientes em aberto:")
                for idx, (name, value) in enumerate(concentration["top_clients"], 1):
                    lines.append(f"  {idx}. {name[:22]} — {_format_brl(value)}")

            if summary["atrasadas"]:
                lines.append("\nTop 5 atrasadas:")
                for i, conta in enumerate(summary["atrasadas"][:5], 1):
                    nome = _short_label(conta.get("pessoa"), conta.get("desc"), max_len=22)
                    lines.append(
                        f"  {i}. {nome} — {_format_brl(conta.get('valor'))} "
                        f"(venc: {_short_date(conta.get('venc'))})"
                    )
            lines.append("\nMetas executivas:")
            lines.append(
                f"- Inadimplência: {targets['inadimplencia_pct']:.1f}% "
                f"(meta <= {targets['meta_inadimplencia_pct']:.1f}%)"
            )
            lines.append(
                f"- Concentração Top 3: {concentration['top_pct']:.1f}% "
                f"(meta <= {targets['meta_concentracao_top3_pct']:.1f}%)"
            )
            trend = _load_cash_risk_trend(history_days=7)
            lines.extend(_format_cfo_trend_lines(trend, markdown=False))
            actions = _build_cfo_action_plan(
                risk_level=str(risk["level"]),
                trend_direction=(trend or {}).get("direction"),
                inadimplencia_ok=bool(targets["inadimplencia_ok"]),
                concentracao_ok=bool(targets["concentracao_ok"]),
            )
            alert_flags = _build_cfo_alert_flags(
                risk_level=str(risk["level"]),
                projected_15d=float(snapshot["projected_15d"]),
                inadimplencia_pct=float(targets["inadimplencia_pct"]),
                meta_inadimplencia_pct=float(targets["meta_inadimplencia_pct"]),
                top3_concentration_pct=float(concentration["top_pct"]),
                meta_concentracao_top3_pct=float(targets["meta_concentracao_top3_pct"]),
                trend_direction=(trend or {}).get("direction"),
                saldos_all_zero=bool(snapshot.get("saldos_all_zero")),
            )
            lines.append("\nAlertas executivos:")
            if alert_flags:
                for flag in alert_flags:
                    lines.append(f"- {flag}")
            else:
                lines.append("- Sem alertas críticos no momento.")
            lines.append("\nPlano de ação imediato:")
            for idx, action in enumerate(actions, 1):
                lines.append(f"{idx}. {action}")
            lines.append(f"Impacto esperado: {targets['impacto']}")
            lines.append(f"\nAção recomendada: {risk['recommendation']}")
        except Exception as exc:
            logger.error(f"Daily CFO alert generation failed: {exc}", exc_info=True)
            lines.append(f"\nErro ao montar alerta diário: {str(exc)[:120]}")

    message = "\n".join(lines)
    for chat_id in chat_ids:
        try:
            await application.bot.send_message(chat_id=chat_id, text=message)
        except Exception as exc:
            logger.error(f"Failed to send daily CFO alert to chat {chat_id}: {exc}", exc_info=True)


def _build_email_billing_alert_lines(
    result: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> List[str]:
    """Build Telegram lines for daily billing email campaign alert."""
    ref_now = now or datetime.now(timezone.utc)
    lines = [f"Alerta Cobrança E-mail ({ref_now.strftime('%d/%m/%Y')})"]

    if bool(result.get("skipped")):
        reason = _as_text(result.get("reason")) or "não informado"
        lines.append(f"\nCampanha não executada: {reason}")
        return lines

    provider = _as_text(result.get("provider")) or "log"
    dry_run = bool(result.get("dry_run"))
    mode = "SIMULAÇÃO" if dry_run else "REAL"
    lines.append(f"\nExecução: {provider}/{mode}")
    lines.append(
        f"Clientes elegíveis: {int(result.get('eligible_clients') or 0)} | "
        f"Registros elegíveis: {int(result.get('eligible_records') or 0)}"
    )
    lines.append(
        f"Enviados: {int(result.get('emails_sent') or 0)} | "
        f"Simulação: {int(result.get('emails_dry_run') or 0)} | "
        f"Falhas: {int(result.get('emails_failed') or 0)}"
    )
    lines.append(
        f"Nível 1: {int((result.get('level_counts') or {}).get('1', 0))} | "
        f"Nível 2: {int((result.get('level_counts') or {}).get('2', 0))} | "
        f"Nível 3: {int((result.get('level_counts') or {}).get('3', 0))}"
    )

    if bool(result.get("test_mode")):
        recipients = [r for r in (result.get("test_recipients") or []) if _as_text(r)]
        if recipients:
            preview = ", ".join(recipients[:3])
            if len(recipients) > 3:
                preview += "..."
            lines.append(f"Destinos de teste: {preview}")

    errors = [err for err in (result.get("errors") or []) if _as_text(err)]
    if errors:
        lines.append("\nErros:")
        for item in errors[:3]:
            lines.append(f"- {_as_text(item)[:160]}")
    else:
        lines.append("\nResultado: campanha concluída sem erros.")

    duration = float(result.get("duration_seconds") or 0.0)
    lines.append(f"Tempo: {duration:.1f}s")
    return lines


async def send_daily_email_billing_alert(application: Application, result: Dict[str, Any]):
    """Send billing email campaign execution summary to Telegram alert chats."""
    if not bool(getattr(settings, "EMAIL_BILLING_ALERT_ENABLED", True)):
        return

    chat_ids = _get_alert_chat_ids()
    if not chat_ids:
        logger.info("Email billing alert skipped: TELEGRAM_ALERT_CHAT_IDS not configured")
        return

    message = "\n".join(_build_email_billing_alert_lines(result))
    for chat_id in chat_ids:
        try:
            await application.bot.send_message(chat_id=chat_id, text=message)
        except Exception as exc:
            logger.error(
                "Failed to send email billing alert to chat %s: %s",
                chat_id,
                exc,
                exc_info=True,
            )


def _build_ai_employee_alert_lines(result: Dict[str, Any]) -> List[str]:
    """Build Telegram summary lines for AI Employee orchestration runs."""
    if bool(result.get("skipped")):
        return [
            "Resumo AI Employee",
            f"Execução não realizada: {_as_text(result.get('reason')) or 'motivo não informado'}",
        ]

    summary = result.get("summary") or {}
    cobrador = summary.get("cobrador") or {}
    contratos = summary.get("contratos") or {}
    cfo = summary.get("cfo_assistant") or {}
    recommendations = list(summary.get("recommended_actions") or [])

    lines = ["Resumo AI Employee"]
    lines.append(
        f"Modo: {_as_text(result.get('mode') or 'builtin')} "
        f"| dry_run: {bool(result.get('dry_run'))}"
    )
    lines.append(
        f"Cobrador: e-mail elegíveis {int(cobrador.get('eligible_email_clients') or 0)} "
        f"| WhatsApp elegíveis {int(cobrador.get('eligible_whatsapp_clients') or 0)} "
        f"| atrasados {int(cobrador.get('overdue_records') or 0)}"
    )
    lines.append(
        f"Contratos: monitorados {int(contratos.get('monitored_total') or 0)} "
        f"| a vencer {int(contratos.get('expiring_soon_count') or 0)} "
        f"| vencidos {int(contratos.get('overdue_count') or 0)}"
    )
    lines.append(
        f"CFO: risco {_as_text(cfo.get('risk_level')).upper() or 'N/D'} "
        f"| projeção 15d {_format_brl(cfo.get('projected_15d') or 0)} "
        f"| tendência {_as_text(cfo.get('trend_direction')).upper() or 'N/D'}"
    )

    if recommendations:
        lines.append("Ações recomendadas:")
        for idx, rec in enumerate(recommendations[:3], 1):
            lines.append(f"{idx}. {_as_text(rec)}")

    errors = list(result.get("errors") or [])
    if errors:
        lines.append(f"Erros: {len(errors)}")
        lines.append(f"Primeiro erro: {_as_text(errors[0])[:180]}")
    else:
        lines.append("Resultado: execução concluída sem erros.")

    return lines


async def send_ai_employee_alert(application: Application, result: Dict[str, Any]):
    """Send AI Employee orchestration summary to Telegram alert chats."""
    if not bool(getattr(settings, "AI_EMPLOYEE_TELEGRAM_ALERT_ENABLED", True)):
        return

    chat_ids = _get_alert_chat_ids()
    if not chat_ids:
        logger.info("AI Employee alert skipped: TELEGRAM_ALERT_CHAT_IDS not configured")
        return

    message = "\n".join(_build_ai_employee_alert_lines(result))
    for chat_id in chat_ids:
        try:
            await application.bot.send_message(chat_id=chat_id, text=message)
        except Exception as exc:
            logger.error(
                "Failed to send AI Employee alert to chat %s: %s",
                chat_id,
                exc,
                exc_info=True,
            )


async def _build_weekly_cfo_summary_lines() -> List[str]:
    """Build weekly CFO summary lines reused by scheduler and manual command."""
    from datetime import datetime, timezone

    lines = [f"Resumo Semanal CFO ({datetime.now(timezone.utc).strftime('%d/%m/%Y')})"]

    access_token, error = await _get_conta_azul_token()
    if error:
        lines.append(f"\nConta Azul indisponível: {error.splitlines()[0]}")
        return lines

    try:
        snapshot = await _build_cfo_snapshot(access_token)
        summary = snapshot["receber_summary_30"]
        risk = snapshot["risk"]
        concentration = snapshot["concentration"]
        targets = _evaluate_cfo_targets(
            total_aberto_30d=float(summary["total_aberto"]),
            total_atrasado_30d=float(summary["total_atrasado"]),
            top3_concentration_pct=float(concentration["top_pct"]),
        )
        trend = _load_cash_risk_trend(history_days=30)

        lines.append(f"\nRisco de caixa atual: {risk['level'].upper()}")
        lines.append(f"Projeção de caixa (15d): {_format_brl(snapshot['projected_15d'])}")
        lines.append(f"Inadimplência da carteira (30d): {targets['inadimplencia_pct']:.1f}%")
        lines.append(f"Concentração Top 3 (30d): {concentration['top_pct']:.1f}%")
        lines.extend(_format_cfo_trend_lines(trend, markdown=False))

        actions = _build_cfo_action_plan(
            risk_level=str(risk["level"]),
            trend_direction=(trend or {}).get("direction"),
            inadimplencia_ok=bool(targets["inadimplencia_ok"]),
            concentracao_ok=bool(targets["concentracao_ok"]),
        )
        alert_flags = _build_cfo_alert_flags(
            risk_level=str(risk["level"]),
            projected_15d=float(snapshot["projected_15d"]),
            inadimplencia_pct=float(targets["inadimplencia_pct"]),
            meta_inadimplencia_pct=float(targets["meta_inadimplencia_pct"]),
            top3_concentration_pct=float(concentration["top_pct"]),
            meta_concentracao_top3_pct=float(targets["meta_concentracao_top3_pct"]),
            trend_direction=(trend or {}).get("direction"),
            saldos_all_zero=bool(snapshot.get("saldos_all_zero")),
        )
        lines.append("\nAlertas executivos:")
        if alert_flags:
            for flag in alert_flags:
                lines.append(f"- {flag}")
        else:
            lines.append("- Sem alertas críticos no momento.")
        lines.append("\nFoco executivo da semana:")
        for idx, action in enumerate(actions, 1):
            lines.append(f"{idx}. {action}")

        if concentration["top_clients"]:
            lines.append("\nTop 3 clientes em aberto:")
            for idx, (name, value) in enumerate(concentration["top_clients"], 1):
                lines.append(f"  {idx}. {name[:22]} — {_format_brl(value)}")

        lines.append(f"\nImpacto esperado: {targets['impacto']}")
    except Exception as exc:
        logger.error(f"Weekly CFO summary generation failed: {exc}", exc_info=True)
        lines.append(f"\nErro ao montar resumo semanal: {str(exc)[:120]}")

    return lines


async def _build_operacao_dia_lines() -> List[str]:
    """Build a concise daily operational summary for CFO supervision."""
    now_ref = datetime.now(timezone.utc)
    lines = [f"Operação do Dia ({now_ref.strftime('%d/%m/%Y %H:%M UTC')})"]

    # 1) Cliente sync health
    try:
        from app.background.sync_clients import get_sync_status

        sync_status = await get_sync_status()
        lines.append("\nClientes:")
        lines.append(
            f"- Base: {int(sync_status.get('total_clients') or 0)} total | "
            f"{int(sync_status.get('synced_clients') or 0)} sincronizados"
        )
        lines.append(
            "- "
            + _client_sync_freshness_line(
                sync_status.get("sync_freshness"),
                sync_status.get("hours_since_last_sync"),
            )
        )
    except Exception as exc:
        logger.error("Daily operation summary failed on client sync: %s", exc, exc_info=True)
        lines.append("\nClientes: indisponível no momento.")

    # 2) Financial sync health
    try:
        from app.background.sync_financial import get_financial_sync_status

        financial = await get_financial_sync_status()
        lines.append("\nFinanceiro:")
        lines.append(
            f"- Registros: {int(financial.get('total_records') or 0)} "
            f"(receber {int(financial.get('receivable_records') or 0)} | "
            f"pagar {int(financial.get('payable_records') or 0)} | "
            f"atrasados {int(financial.get('overdue_records') or 0)})"
        )
        freshness_note = _financial_sync_freshness(financial.get("last_sync_time"))
        if freshness_note:
            lines.append(f"- {freshness_note}")
    except Exception as exc:
        logger.error("Daily operation summary failed on financial sync: %s", exc, exc_info=True)
        lines.append("\nFinanceiro: indisponível no momento.")

    # 3) Cash risk quick view
    access_token, token_error = await _get_conta_azul_token()
    if token_error:
        first_line = _as_text(token_error).splitlines()[0] if _as_text(token_error) else "indisponível"
        lines.append(f"\nRisco e caixa: indisponível ({first_line[:140]})")
    elif access_token:
        try:
            snapshot = await _build_cfo_snapshot(access_token)
            concentration = snapshot["concentration"]
            summary_30 = snapshot["receber_summary_30"]
            risk = snapshot["risk"]
            targets = _evaluate_cfo_targets(
                total_aberto_30d=float(summary_30["total_aberto"]),
                total_atrasado_30d=float(summary_30["total_atrasado"]),
                top3_concentration_pct=float(concentration["top_pct"]),
            )
            trend = _load_cash_risk_trend(history_days=7)
            trend_map = {
                "improving": "MELHORANDO",
                "worsening": "PIORANDO",
                "stable": "ESTÁVEL",
            }
            trend_label = trend_map.get(_as_text((trend or {}).get("direction")).lower(), "SEM BASE")

            lines.append("\nRisco e caixa:")
            lines.append(
                f"- Risco: {str(risk.get('level', '')).upper()} | "
                f"Projeção 15d: {_format_brl(snapshot['projected_15d'])}"
            )
            lines.append(
                f"- Inadimplência 30d: {targets['inadimplencia_pct']:.1f}% "
                f"(meta <= {targets['meta_inadimplencia_pct']:.1f}%)"
            )
            lines.append(
                f"- Concentração Top 3: {concentration['top_pct']:.1f}% "
                f"(meta <= {targets['meta_concentracao_top3_pct']:.1f}%)"
            )
            lines.append(f"- Tendência 7d: {trend_label}")
        except Exception as exc:
            logger.error("Daily operation summary failed on CFO snapshot: %s", exc, exc_info=True)
            lines.append("\nRisco e caixa: indisponível no momento.")

    # 4) Billing email operation
    if settings.EMAIL_BILLING_ENABLED:
        provider = (settings.EMAIL_BILLING_PROVIDER or "log").strip().lower()
        schedule = f"{settings.EMAIL_BILLING_HOUR:02d}:{settings.EMAIL_BILLING_MINUTE:02d}"
        real_send_enabled = bool(getattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", False))
        real_send_status = "LIBERADO" if real_send_enabled else "STANDBY"

        lines.append("\nCobrança e-mail:")
        lines.append(
            f"- Execução: {provider}/simulação ({schedule}) | envio real: {real_send_status}"
        )
        try:
            from app.services.email_billing_service import run_billing_email_campaign

            dry_result = await run_billing_email_campaign(dry_run=True)
            level_counts = dry_result.get("level_counts") or {}
            lines.append(
                f"- Elegíveis: {int(dry_result.get('eligible_clients') or 0)} clientes | "
                f"{int(dry_result.get('eligible_records') or 0)} títulos"
            )
            lines.append(
                f"- Nível 2: {int(level_counts.get('2', 0))} | "
                f"Nível 3: {int(level_counts.get('3', 0))}"
            )
        except Exception as exc:
            logger.error("Daily operation summary failed on email billing preview: %s", exc, exc_info=True)
            lines.append("- Prévia de elegibilidade indisponível.")
    else:
        lines.append("\nCobrança e-mail: desativada.")

    # 5) Contract lifecycle quick health
    try:
        from app.services.contract_lifecycle_service import build_contract_lifecycle_snapshot

        window_days = int(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_DAYS", 30))
        with _db_session_scope() as db:
            lifecycle_snapshot = build_contract_lifecycle_snapshot(db, days_ahead=window_days)

        overdue = list(lifecycle_snapshot.get("overdue") or [])
        expiring = list(lifecycle_snapshot.get("expiring_soon") or [])
        missing = list(lifecycle_snapshot.get("missing_end_date") or [])

        lines.append("\nCiclo de contratos:")
        lines.append(
            f"- Janela: {window_days}d | monitorados: {int(lifecycle_snapshot.get('monitored_total') or 0)} | "
            f"vencidos: {len(overdue)} | a vencer: {len(expiring)} | sem data fim: {len(missing)}"
        )
        if expiring:
            first = expiring[0]
            lines.append(
                f"- Próximo vencimento: {first.get('contract_number')} em "
                f"{int(first.get('days_to_end') or 0)} dia(s)"
            )
    except Exception as exc:
        logger.error("Daily operation summary failed on contract lifecycle: %s", exc, exc_info=True)
        lines.append("\nCiclo de contratos: indisponível no momento.")

    lines.append("\nPróximo passo: use /cfo para análise executiva completa.")
    return lines


async def cmd_operacao_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a compact daily operation summary for CFO follow-up."""
    _ = context
    await update.message.reply_text("Montando operação do dia...")
    try:
        lines = await _build_operacao_dia_lines()
        await update.message.reply_text("\n".join(lines))
    except Exception as exc:
        logger.error("Error building daily operation summary: %s", exc, exc_info=True)
        await update.message.reply_text(f"❌ Erro ao montar operação do dia: {str(exc)[:180]}")


async def send_weekly_cfo_alert(application: Application):
    """Send weekly executive summary to configured Telegram chats."""
    chat_ids = _get_alert_chat_ids()
    if not chat_ids:
        logger.info("Weekly CFO alert skipped: TELEGRAM_ALERT_CHAT_IDS not configured")
        return

    lines = await _build_weekly_cfo_summary_lines()
    message = "\n".join(lines)
    for chat_id in chat_ids:
        try:
            await application.bot.send_message(chat_id=chat_id, text=message)
        except Exception as exc:
            logger.error(f"Failed to send weekly CFO alert to chat {chat_id}: {exc}", exc_info=True)


async def cmd_resumo_semanal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate weekly CFO summary immediately for the current chat."""
    _ = context  # Signature compatibility
    await update.message.reply_text("Montando resumo semanal CFO...")
    lines = await _build_weekly_cfo_summary_lines()
    await update.message.reply_text("\n".join(lines))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check integration status."""
    statuses = []
    conta_azul_access_token = None

    # Check database
    try:
        with _db_session_scope() as db:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
        statuses.append("Banco de dados: Conectado")
    except Exception:
        statuses.append("Banco de dados: Desconectado")

    # Check AI provider stack
    try:
        _ = get_claude()
        primary_provider = (settings.AI_PROVIDER or "anthropic").strip().lower()
        provider_model_map = {
            "anthropic": settings.ANTHROPIC_MODEL,
            "gemini": settings.GEMINI_MODEL,
            "openai": settings.OPENAI_MODEL,
        }
        primary_model = provider_model_map.get(primary_provider, settings.ANTHROPIC_MODEL)
        statuses.append(f"IA: Conectada ({primary_provider}/{primary_model})")

        fallback_options: List[str] = []
        if (settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY) and primary_provider != "gemini":
            fallback_options.append(f"gemini/{settings.GEMINI_MODEL}")
        if settings.ANTHROPIC_API_KEY and primary_provider != "anthropic":
            fallback_options.append(f"anthropic/{settings.ANTHROPIC_MODEL}")
        if settings.OPENAI_API_KEY and primary_provider != "openai":
            fallback_options.append(f"openai/{settings.OPENAI_MODEL}")
        if fallback_options:
            statuses.append("IA fallback: " + ", ".join(fallback_options))
    except Exception:
        statuses.append("IA: Erro na configuração")

    # AI Employee orchestration status
    if bool(getattr(settings, "AI_EMPLOYEE_ENABLED", False)):
        runtime_status = None
        try:
            from app.agents.orchestrator import AIEmployeeOrchestrator

            runtime_status = AIEmployeeOrchestrator().runtime_status()
        except Exception:
            runtime_status = None

        if runtime_status:
            statuses.append(
                "AI Employee: Ativo "
                f"(runtime={runtime_status.get('runtime_engine')} | "
                f"solicitado={runtime_status.get('requested_engine')} | "
                f"crew_exec={runtime_status.get('crewai_execution_enabled')} | "
                f"dry_run={runtime_status.get('dry_run')})"
            )
            if runtime_status.get("engine_degraded"):
                statuses.append(
                    "AI Employee fallback: "
                    f"{runtime_status.get('runtime_reason', 'fallback_to_builtin')}"
                )
        else:
            statuses.append(
                "AI Employee: Ativo "
                f"({getattr(settings, 'AI_EMPLOYEE_ORCHESTRATION_ENGINE', 'builtin')}/"
                f"dry_run={bool(getattr(settings, 'AI_EMPLOYEE_DRY_RUN', True))})"
            )
        if bool(getattr(settings, "AI_EMPLOYEE_DAILY_SUMMARY_ENABLED", False)):
            statuses.append(
                "AI Employee diário: Ativo "
                f"({int(getattr(settings, 'AI_EMPLOYEE_DAILY_HOUR', 8)):02d}:"
                f"{int(getattr(settings, 'AI_EMPLOYEE_DAILY_MINUTE', 20)):02d})"
            )
        else:
            statuses.append("AI Employee diário: Desativado (execução manual)")
    else:
        statuses.append("AI Employee: Desativado")

    # Check Conta Azul token (with proactive refresh)
    try:
        conta_azul_access_token, token_error = await _get_conta_azul_token()

        if conta_azul_access_token:
            expiry_info = _get_conta_azul_token_expiry_info()
            if expiry_info:
                eta_text = _format_expiry_eta(int(expiry_info["seconds_to_expiry"]))
                expires_at_text = expiry_info["expires_at"].strftime("%Y-%m-%d %H:%M UTC")
                if int(expiry_info["seconds_to_expiry"]) <= 86400:
                    statuses.append(
                        "Conta Azul: Token ativo (atenção: "
                        f"{eta_text}, vence em {expires_at_text})"
                    )
                else:
                    statuses.append(
                        f"Conta Azul: Token ativo ({eta_text}, vence em {expires_at_text})"
                    )
            else:
                statuses.append("Conta Azul: Token ativo")
        elif token_error:
            msg = token_error.lower()
            if "invalid_grant" in msg or "reconectar" in msg or "reautorizar" in msg:
                statuses.append(
                    "Conta Azul: Token expirado\n"
                    "Reconectar: use /reconectar"
                )
            elif "não conectado" in msg or "nao conectado" in msg:
                statuses.append(
                    "Conta Azul: Não autorizado\n"
                    "Conectar: use /reconectar"
                )
            else:
                statuses.append("Conta Azul: Não foi possível validar token no momento")
        else:
            statuses.append(
                "Conta Azul: Não autorizado\n"
                "Conectar: use /reconectar"
            )
    except Exception:
        statuses.append("Conta Azul: Verificação indisponível")

    # Autentique
    if settings.AUTENTIQUE_API_KEY:
        statuses.append("Autentique: Configurado")
        if bool(getattr(settings, "AUTENTIQUE_SIGNATURE_SYNC_ENABLED", True)):
            statuses.append(
                "Sync assinaturas Autentique: Ativo "
                f"(a cada {int(getattr(settings, 'AUTENTIQUE_SIGNATURE_SYNC_INTERVAL_MINUTES', 30))} min, "
                f"lote {int(getattr(settings, 'AUTENTIQUE_SIGNATURE_SYNC_MAX_CONTRACTS', 100))})"
            )
        else:
            statuses.append("Sync assinaturas Autentique: Desativado")
        if bool(getattr(settings, "AUTENTIQUE_WEBHOOK_ENABLED", True)):
            webhook_mode = "com segredo" if _as_text(getattr(settings, "AUTENTIQUE_WEBHOOK_SECRET", "")) else "sem segredo"
            statuses.append(f"Webhook Autentique: Ativo ({webhook_mode})")
        else:
            statuses.append("Webhook Autentique: Desativado")
    else:
        statuses.append("Autentique: API key não configurada")

    # Billing email campaign status
    email_schedule = f"{settings.EMAIL_BILLING_HOUR:02d}:{settings.EMAIL_BILLING_MINUTE:02d}"
    email_test_recipients = _parse_email_test_recipients(
        getattr(settings, "EMAIL_BILLING_TEST_RECIPIENTS", "")
    )
    if settings.EMAIL_BILLING_ENABLED:
        provider = (settings.EMAIL_BILLING_PROVIDER or "log").strip().lower()
        mode = "simulação" if settings.EMAIL_BILLING_DRY_RUN else "ativo"
        if email_test_recipients:
            mode = f"{mode}/teste"
        if provider == "sendgrid":
            if settings.SENDGRID_API_KEY and settings.EMAIL_BILLING_FROM:
                statuses.append(
                    f"Cobrança e-mail: Configurada ({provider}/{mode} {email_schedule})"
                )
            else:
                statuses.append(
                    "Cobrança e-mail: Habilitada com configuração incompleta "
                    "(defina SENDGRID_API_KEY e EMAIL_BILLING_FROM)"
                )
        else:
            statuses.append(
                f"Cobrança e-mail: Configurada ({provider}/{mode} {email_schedule})"
            )
        if bool(getattr(settings, "EMAIL_BILLING_REAL_SEND_ENABLED", False)):
            statuses.append("Cobrança e-mail: Envio manual com /cobrar_email confirmar")
        else:
            statuses.append("Cobrança e-mail: Standby (envio real bloqueado)")
        if bool(getattr(settings, "EMAIL_BILLING_ALERT_ENABLED", True)):
            if _get_alert_chat_ids():
                statuses.append("Alerta cobrança e-mail Telegram: Ativo")
            else:
                statuses.append(
                    "Alerta cobrança e-mail Telegram: Desativado (sem chats configurados)"
                )
        else:
            statuses.append("Alerta cobrança e-mail Telegram: Desativado")
        if email_test_recipients:
            statuses.append(
                "Cobrança e-mail: Destinos de teste "
                + ", ".join(email_test_recipients[:3])
                + ("..." if len(email_test_recipients) > 3 else "")
            )
    else:
        statuses.append("Cobrança e-mail: Desativada")

    # WhatsApp billing campaign status
    wa_schedule = f"{settings.WHATSAPP_BILLING_HOUR:02d}:{settings.WHATSAPP_BILLING_MINUTE:02d}"
    if not _is_whatsapp_phase_enabled():
        statuses.append("Cobrança WhatsApp: Adiada para fase final (teste simulado)")
    elif settings.WHATSAPP_BILLING_ENABLED:
        wa_provider = (settings.WHATSAPP_BILLING_PROVIDER or "log").strip().lower()
        wa_mode = "simulação" if settings.WHATSAPP_BILLING_DRY_RUN else "ativo"
        if bool(getattr(settings, "WHATSAPP_BILLING_REQUIRE_CONFIRMATION", True)):
            wa_mode = f"{wa_mode}/aprovação"
        if wa_provider == "waha":
            if settings.WHATSAPP_WAHA_URL:
                statuses.append(
                    f"Cobrança WhatsApp: Configurada ({wa_provider}/{wa_mode} {wa_schedule})"
                )
                if bool(getattr(settings, "WHATSAPP_BILLING_REQUIRE_CONFIRMATION", True)):
                    statuses.append("Cobrança WhatsApp: Envio manual com /cobrar_whatsapp confirmar")
                try:
                    from app.services.whatsapp_billing_service import list_blocked_whatsapp_targets

                    blocked_count = len(list_blocked_whatsapp_targets(limit=500))
                    if blocked_count > 0:
                        statuses.append(
                            f"Cobrança WhatsApp: {blocked_count} número(s) em quarentena (LID)"
                        )
                except Exception:
                    pass
            else:
                statuses.append(
                    "Cobrança WhatsApp: Habilitada com configuração incompleta "
                    "(defina WHATSAPP_WAHA_URL)"
                )
        else:
            statuses.append(
                f"Cobrança WhatsApp: Configurada ({wa_provider}/{wa_mode} {wa_schedule})"
            )
    else:
        statuses.append("Cobrança WhatsApp: Desativada")

    # Contract lifecycle automation status
    lifecycle_enabled = bool(getattr(settings, "CONTRACT_LIFECYCLE_ENABLED", True))
    lifecycle_alert_enabled = bool(getattr(settings, "CONTRACT_LIFECYCLE_ALERT_ENABLED", True))
    if lifecycle_enabled:
        statuses.append(
            "Ciclo de contratos: Ativo "
            f"({settings.CONTRACT_LIFECYCLE_RUN_HOUR:02d}:{settings.CONTRACT_LIFECYCLE_RUN_MINUTE:02d})"
        )
        if lifecycle_alert_enabled:
            statuses.append(
                "Alerta ciclo contratos: Ativo "
                f"({settings.CONTRACT_LIFECYCLE_ALERT_HOUR:02d}:{settings.CONTRACT_LIFECYCLE_ALERT_MINUTE:02d}, "
                f"janela {settings.CONTRACT_LIFECYCLE_ALERT_DAYS}d)"
            )
        else:
            statuses.append("Alerta ciclo contratos: Desativado")
    else:
        statuses.append("Ciclo de contratos: Desativado")

    # Daily CFO alert status
    if _get_alert_chat_ids():
        statuses.append(
            "Alerta diário Telegram: Configurado "
            f"({settings.TELEGRAM_ALERT_HOUR:02d}:{settings.TELEGRAM_ALERT_MINUTE:02d})"
        )
        if settings.TELEGRAM_WEEKLY_ALERT_ENABLED:
            statuses.append(
                "Resumo semanal Telegram: Configurado "
                f"({settings.TELEGRAM_WEEKLY_ALERT_DAY} "
                f"{settings.TELEGRAM_WEEKLY_ALERT_HOUR:02d}:{settings.TELEGRAM_WEEKLY_ALERT_MINUTE:02d})"
            )
        else:
            statuses.append("Resumo semanal Telegram: Desativado")
    else:
        statuses.append("Alerta diário Telegram: Desativado (defina TELEGRAM_ALERT_CHAT_IDS)")
        statuses.append("Resumo semanal Telegram: Desativado (sem chats configurados)")

    # Sync status
    try:
        from app.background.sync_clients import get_sync_status
        sync_status = await get_sync_status()
        statuses.append(
            f"\nClientes: {sync_status['total_clients']} total | "
            f"{sync_status['synced_clients']} sincronizados"
        )
        if sync_status['last_sync_time']:
            statuses.append(f"Última sincronização: {sync_status['last_sync_time'][:19]}")
            freshness = (sync_status.get("sync_freshness") or "").lower()
            hours = sync_status.get("hours_since_last_sync")
            if freshness == "stale":
                statuses.append(
                    f"Saúde sync clientes: Defasada ({float(hours or 0.0):.1f}h sem atualizar)"
                )
            elif freshness == "warning":
                statuses.append(
                    f"Saúde sync clientes: Atenção ({float(hours or 0.0):.1f}h sem atualizar)"
                )
            elif freshness == "fresh":
                statuses.append(
                    f"Saúde sync clientes: Atualizada ({float(hours or 0.0):.1f}h)"
                )
        else:
            statuses.append("Saúde sync clientes: Sem histórico de sincronização")
    except Exception:
        pass

    # Financial sync status
    try:
        from app.background.sync_financial import get_financial_sync_status

        financial_status = await get_financial_sync_status()
        statuses.append(
            f"\nFinanceiro: {financial_status['total_records']} registros | "
            f"{financial_status['synced_records']} sincronizados"
        )
        statuses.append(
            f"Receber: {financial_status['receivable_records']} | "
            f"Pagar: {financial_status['payable_records']} | "
            f"Atrasados: {financial_status['overdue_records']}"
        )
        if financial_status["last_sync_time"]:
            statuses.append(
                f"Última sync financeira: {financial_status['last_sync_time'][:19]}"
            )
        freshness_note = _financial_sync_freshness(financial_status.get("last_sync_time"))
        if freshness_note:
            statuses.append(freshness_note)
    except Exception:
        pass

    # Executive quick view
    try:
        if conta_azul_access_token:
            snapshot = await _build_cfo_snapshot(conta_azul_access_token)
            risk = snapshot["risk"]
            statuses.append(
                f"\nRisco de caixa: {risk['level'].upper()}"
            )
            statuses.append(
                f"Projeção de caixa (15d): {_format_brl(snapshot['projected_15d'])}"
            )
            if snapshot.get("saldos_all_zero"):
                statuses.append("Alerta: todas as contas ativas retornaram saldo R$ 0,00")
    except Exception:
        pass

    await update.message.reply_text("Status das Integrações:\n\n" + "\n".join(statuses))


# ─── Message Handler (Conversation with AI) ──────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages - route to active conversation or free chat."""
    chat_id = update.effective_chat.id
    user_text = update.message.text

    if not user_text:
        return

    try:
        if chat_id not in pending_client_onboarding:
            persisted_client_onboarding = _load_persisted_client_onboarding(chat_id)
            if persisted_client_onboarding:
                pending_client_onboarding[chat_id] = persisted_client_onboarding

        if chat_id in pending_client_onboarding:
            normalized = _as_text(user_text).lower()
            if normalized in {"/cancelar", "cancelar"}:
                pending_client_onboarding.pop(chat_id, None)
                _clear_persisted_client_onboarding(chat_id)
                await update.message.reply_text(
                    "❌ Cadastro de cliente cancelado. O contrato não foi salvo."
                )
                return

            state = pending_client_onboarding.get(chat_id, {})
            step = _as_text(state.get("step")).lower()
            contract_data = dict(state.get("contract_data") or {})
            client_payload = dict(state.get("client_payload") or {})

            if step == "confirm":
                if _is_affirmative_answer(user_text):
                    state["step"] = "email"
                    pending_client_onboarding[chat_id] = state
                    _save_persisted_client_onboarding(chat_id, state)
                    await update.message.reply_text(
                        "Perfeito. Informe o e-mail do cliente (ou digite 'pular')."
                    )
                elif _is_negative_answer(user_text):
                    pending_client_onboarding.pop(chat_id, None)
                    _clear_persisted_client_onboarding(chat_id)
                    await update.message.reply_text(
                        "Sem problemas. O contrato não foi salvo.\n"
                        "Quando quiser, cadastre o cliente e rode /novo_contrato novamente."
                    )
                else:
                    await update.message.reply_text(
                        "Responda com 'sim' para cadastrar o cliente agora ou 'não' para cancelar."
                    )
                return

            if step == "email":
                if _is_skip_answer(user_text):
                    client_payload["email"] = ""
                else:
                    email = _as_text(user_text).lower()
                    if not _is_valid_email(email):
                        await update.message.reply_text(
                            "E-mail inválido. Informe um e-mail válido ou digite 'pular'."
                        )
                        return
                    client_payload["email"] = _truncate_text(email, 255)

                state["client_payload"] = client_payload
                state["step"] = "phone"
                pending_client_onboarding[chat_id] = state
                _save_persisted_client_onboarding(chat_id, state)
                await update.message.reply_text(
                    "Agora informe o telefone do cliente (ou digite 'pular')."
                )
                return

            if step == "phone":
                if _is_skip_answer(user_text):
                    client_payload["phone"] = ""
                else:
                    client_payload["phone"] = _truncate_text(user_text, 20)

                client_name = _truncate_text(
                    client_payload.get("name") or contract_data.get("client_name"),
                    255,
                )
                cpf_cnpj = _normalize_client_tax_id(
                    client_payload.get("cpf_cnpj") or contract_data.get("cpf_cnpj")
                )

                if not client_name or not cpf_cnpj:
                    pending_client_onboarding.pop(chat_id, None)
                    _clear_persisted_client_onboarding(chat_id)
                    await update.message.reply_text(
                        "⚠️ Não foi possível cadastrar o cliente: nome ou CPF/CNPJ ausente.\n"
                        "Rode /novo_contrato novamente e informe esses dados."
                    )
                    return

                try:
                    with _db_session_scope() as db:
                        client = db.query(Client).filter_by(cpf_cnpj=cpf_cnpj).first()
                        if not client:
                            client = Client(
                                name=client_name,
                                cpf_cnpj=cpf_cnpj,
                                email=_truncate_text(client_payload.get("email"), 255) or None,
                                phone=_truncate_text(client_payload.get("phone"), 20) or None,
                                notes="Cliente criado automaticamente via fluxo Telegram /novo_contrato",
                            )
                            db.add(client)
                            db.flush()
                        contract_number = _save_contract_draft(db, client.id, contract_data)

                    pending_client_onboarding.pop(chat_id, None)
                    _clear_persisted_client_onboarding(chat_id)
                    await update.message.reply_text(
                        f"✅ Cliente cadastrado e contrato {contract_number} salvo como rascunho!"
                    )
                except Exception as exc:
                    logger.error("Error creating client+contract from onboarding: %s", exc, exc_info=True)
                    pending_client_onboarding.pop(chat_id, None)
                    _clear_persisted_client_onboarding(chat_id)
                    await update.message.reply_text(
                        "⚠️ Houve erro ao finalizar cadastro do cliente e salvar o contrato."
                    )
                return

            pending_client_onboarding.pop(chat_id, None)
            _clear_persisted_client_onboarding(chat_id)

        if chat_id not in pending_period_requests:
            persisted_flow = _load_persisted_period_flow(chat_id)
            if persisted_flow:
                pending_period_requests[chat_id] = persisted_flow

        if chat_id in pending_period_requests:
            flow = pending_period_requests.get(chat_id)
            normalized = _as_text(user_text).lower()

            if normalized in {"/cancelar", "cancelar"}:
                pending_period_requests.pop(chat_id, None)
                _clear_persisted_period_flow(chat_id)
                await update.message.reply_text("❌ Seleção de período cancelada.")
                return

            try:
                data_de, data_ate, label = _parse_period_input(user_text)
            except ValueError as exc:
                await update.message.reply_text(f"⚠️ {exc}\n\n{_period_prompt_text(flow or 'receber')}")
                return

            pending_period_requests.pop(chat_id, None)
            _clear_persisted_period_flow(chat_id)
            if flow == "pagar":
                await _send_contas_pagar_report(update, data_de, data_ate, label)
            elif flow == "sync_financeiro":
                await _send_sync_financeiro_report(update, data_de, data_ate, label)
            else:
                await _send_contas_receber_report(update, data_de, data_ate, label)
            return

        service = get_claude()

        # Hydrate active contract flow from DB if process restarted.
        if chat_id not in active_conversations:
            persisted_history = _load_persisted_contract_history(chat_id)
            if persisted_history:
                active_conversations[chat_id] = persisted_history

        # Check if user has an active contract conversation
        if chat_id in active_conversations:
            history = active_conversations[chat_id]
            history.append({"role": "user", "content": user_text})
            _save_persisted_contract_history(chat_id, history)

            await update.message.reply_chat_action("typing")
            result = await service.collect_contract_data(history)

            if result.get("complete"):
                # Contract data collection complete
                contract_data = result["data"]
                del active_conversations[chat_id]
                _clear_persisted_contract_history(chat_id)

                # Format collected data for confirmation
                await update.message.reply_text(
                    "✅ *Dados do contrato coletados!*\n\n"
                    f"👤 Cliente: *{contract_data.get('client_name', 'N/A')}*\n"
                    f"📋 CPF/CNPJ: {contract_data.get('cpf_cnpj', 'N/A')}\n"
                    f"📝 Serviço: {contract_data.get('service_description', 'N/A')}\n"
                    f"💰 Valor: R$ {contract_data.get('contract_value', 0):,.2f}\n"
                    f"💳 Pagamento: {contract_data.get('payment_terms', 'N/A')}\n"
                    f"📅 Início: {contract_data.get('start_date', 'N/A')}\n"
                    f"⏱ Duração: {contract_data.get('duration_months', 0)} meses\n"
                    f"📌 Cláusulas: {contract_data.get('special_clauses', 'Nenhuma')}\n\n"
                    "O contrato está pronto para ser gerado em PDF e enviado para assinatura!",
                    parse_mode="Markdown"
                )

                # Save to database
                try:
                    with _db_session_scope() as db:
                        normalized_contract = _build_contract_payload(contract_data)
                        cpf_cnpj = normalized_contract.get("cpf_cnpj")
                        client = db.query(Client).filter_by(cpf_cnpj=cpf_cnpj).first() if cpf_cnpj else None

                        if not client:
                            onboarding_state = _build_client_onboarding_state(contract_data)
                            pending_client_onboarding[chat_id] = onboarding_state
                            _save_persisted_client_onboarding(chat_id, onboarding_state)
                            await update.message.reply_text(
                                "⚠️ Cliente não encontrado no sistema.\n"
                                "Deseja cadastrar agora com os dados coletados? Responda 'sim' ou 'não'."
                            )
                        else:
                            contract_number = _save_contract_draft(db, client.id, normalized_contract)
                            await update.message.reply_text(
                                f"💾 Contrato {contract_number} salvo como rascunho no sistema!"
                            )
                except Exception as e:
                    logger.error(f"Error saving contract: {e}")
                    await update.message.reply_text(
                        "⚠️ Dados coletados mas houve erro ao salvar. "
                        "Use a API para registrar manualmente."
                    )
            else:
                # Continue conversation
                history.append({"role": "assistant", "content": result["message"]})
                _save_persisted_contract_history(chat_id, history)
                await update.message.reply_text(result["message"])

        else:
            # Free chat with Claude (not in contract flow)
            await update.message.reply_chat_action("typing")
            email_guidance = "• Cobrança e-mail — desativada nesta etapa\n"
            if settings.EMAIL_BILLING_ENABLED:
                email_guidance = (
                    "• /cobrar_email — Prévia e confirmação da cobrança por e-mail\n"
                    "• /resumo_cobranca — Resumo operacional da cobrança por e-mail\n"
                )
            whatsapp_guidance = "• WhatsApp — adiado para fase final (teste simulado)\n"
            if _is_whatsapp_phase_enabled():
                whatsapp_guidance = (
                    "• /cobrar_whatsapp — Prévia e confirmação da cobrança WhatsApp\n"
                    "• /wa_bloqueados — Números bloqueados automaticamente no WAHA\n"
                    "• /wa_desbloquear — Limpar bloqueio de números WAHA\n"
                )
            legal_sources: List[Dict[str, str]] = []
            legal_prompt_addendum = ""
            if legal_knowledge_service.is_legal_query(user_text):
                legal_grounding = legal_knowledge_service.build_prompt_block(user_text)
                if not legal_grounding.get("has_evidence"):
                    await update.message.reply_text(legal_knowledge_service.no_evidence_message())
                    return
                legal_sources = list(legal_grounding.get("sources") or [])
                legal_prompt_addendum = (
                    "\n\nBASE JURÍDICA CURADA (USO OBRIGATÓRIO NESTA RESPOSTA):\n"
                    f"{legal_grounding.get('prompt_block', '')}\n\n"
                    "REGRAS EXTRAS PARA RESPOSTA JURÍDICA:\n"
                    "• Use somente a base jurídica acima como fundamento normativo\n"
                    "• Cite explicitamente [FONTE 1], [FONTE 2], etc., em cada conclusão normativa\n"
                    "• Se a base não cobrir algum ponto, escreva literalmente: "
                    "'Base normativa não localizada com segurança'\n"
                    "• Não invente artigo, lei, jurisprudência ou entendimento não presente na base acima\n"
                    "• Reforce validação com jurídico humano para decisão final\n"
                )
            response = await service.send_message(
                message=user_text,
                system_prompt=(
                    "Você é o assistente financeiro da AISATEC no Telegram. "
                    "Responda sempre em português brasileiro (pt-BR), de forma clara e objetiva.\n"
                    "Não misture inglês e não use emojis.\n\n"
                    "IMPORTANTE: Você NÃO tem acesso direto ao Conta Azul, banco de dados "
                    "ou qualquer sistema externo nesta conversa. Você NÃO pode consultar "
                    "dados de clientes, saldos, contas ou contratos por conta própria.\n\n"
                    "REGRAS DE CONFIABILIDADE (OBRIGATÓRIAS):\n"
                    "• Nunca invente leis, artigos, jurisprudência, súmulas, decisões ou números de processo\n"
                    "• Nunca apresente hipótese como fato confirmado\n"
                    "• Se faltar base confiável, diga explicitamente que não sabe com segurança e recomende validação jurídica humana\n"
                    "• Quando faltar contexto, faça perguntas objetivas antes de concluir\n"
                    "• Em temas jurídicos, atue como apoio informativo e não como substituto de parecer jurídico formal\n\n"
                    "FORMATO PARA DÚVIDA JURÍDICA (sempre que aplicável):\n"
                    "1) Entendimento preliminar do caso\n"
                    "2) Base normativa confirmada (somente se houver certeza; se não houver, escrever: 'Base normativa não localizada com segurança')\n"
                    "3) Riscos e limites da orientação\n"
                    "4) Próximo passo recomendado (incluindo validação com jurídico humano)\n"
                    "5) Nível de confiança: alto/médio/baixo\n\n"
                    "Quando o usuário pedir dados financeiros ou operações, NÃO finja que "
                    "vai acessar sistemas, NÃO peça confirmação para acessar dados, e NÃO "
                    "invente números. Em vez disso, oriente o usuário a usar o comando correto:\n"
                    "• /clientes — Ver clientes cadastrados\n"
                    "• /contratos — Ver contratos\n"
                    "• /templates_contrato — Ver templates de contrato\n"
                    "• /preview_contrato <id> [template] — Prévia HTML de contrato\n"
                    "• /pdf_contrato <id> [template] — Gerar PDF de contrato\n"
                    "• /contratos_vencendo — Ciclo de vencimento dos contratos\n"
                    "• /sync_assinaturas — Sincronizar status de assinaturas Autentique\n"
                    "• /novo_contrato — Criar contrato com IA\n"
                    "• /sincronizar — Puxar clientes do Conta Azul\n"
                    "• /receber — Contas a receber\n"
                    "• /pagar — Contas a pagar\n"
                    "• /saldos — Saldos das contas financeiras\n"
                    "• /cfo — Painel executivo de risco e projeção\n"
                    "• /operacao_dia — Visão diária consolidada da operação\n"
                    "• /resumo_semanal — Resumo executivo semanal\n"
                    f"{email_guidance}"
                    f"{whatsapp_guidance}"
                    "• /sync_financeiro — Forçar sincronização financeira (ex.: /sync_financeiro 30d)\n"
                    "• /inadimplencia — Parcelas em atraso\n"
                    "• /dashboard — Métricas financeiras\n"
                    "• /status — Status das integrações\n\n"
                    "Você pode ajudar com dúvidas gerais sobre finanças, contratos, "
                    "gestão e uso do sistema, sempre separando claramente: fatos confirmados, "
                    "suposições e pontos que exigem validação."
                    f"{legal_prompt_addendum}"
                )
            )
            if legal_sources and "[FONTE" not in response.upper():
                response = (
                    "Não consegui gerar resposta jurídica com citação explícita das fontes internas, "
                    "então não posso afirmar isso com segurança.\n\n"
                    "Próximo passo: valide com jurídico humano ou refine a pergunta com mais contexto "
                    "(tipo de contrato, cláusula e cenário).\n\n"
                    "Fontes internas disponíveis:\n"
                    + "\n".join(
                        f"- [{src.get('label', 'FONTE')}] {src.get('title', 'Referência legal')}"
                        for src in legal_sources
                    )
                )
            await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(
            "⚠️ Ocorreu um erro ao processar sua mensagem. Tente novamente."
        )


# ─── Bot Setup ────────────────────────────────────────────────────────

async def setup_commands(application: Application):
    """Set bot commands menu in Telegram."""
    commands = [
        BotCommand("start", "Iniciar e ver menu"),
        BotCommand("novo_contrato", "Criar contrato com IA"),
        BotCommand("reconectar", "Reconectar Conta Azul"),
        BotCommand("clientes", "Ver clientes"),
        BotCommand("contratos", "Ver contratos"),
        BotCommand("templates_contrato", "Templates de contrato"),
        BotCommand("preview_contrato", "Prévia HTML contrato"),
        BotCommand("pdf_contrato", "Gerar PDF contrato"),
        BotCommand("contratos_vencendo", "Ciclo de contratos"),
        BotCommand("sync_assinaturas", "Sincronizar assinaturas"),
        BotCommand("sincronizar", "Puxar clientes do Conta Azul"),
        BotCommand("sync_financeiro", "Sincronizar financeiro"),
        BotCommand("receber", "Contas a receber"),
        BotCommand("pagar", "Contas a pagar"),
        BotCommand("saldos", "Saldos das contas"),
        BotCommand("cfo", "Painel executivo CFO"),
        BotCommand("operacao_dia", "Operação diária"),
        BotCommand("resumo_semanal", "Resumo semanal CFO"),
        BotCommand("inadimplencia", "Parcelas atrasadas"),
        BotCommand("dashboard", "Métricas financeiras"),
        BotCommand("status", "Status das integrações"),
        BotCommand("cancelar", "Cancelar conversa atual"),
        BotCommand("ajuda", "Ajuda completa"),
    ]
    if settings.EMAIL_BILLING_ENABLED:
        commands.append(BotCommand("cobrar_email", "Prévia cobrança e-mail"))
        commands.append(BotCommand("resumo_cobranca", "Resumo cobrança e-mail"))
    if _is_whatsapp_phase_enabled():
        commands.extend(
            [
                BotCommand("cobrar_whatsapp", "Prévia cobrança WhatsApp"),
                BotCommand("wa_bloqueados", "Números bloqueados WAHA"),
                BotCommand("wa_desbloquear", "Desbloquear números WAHA"),
            ]
        )
    await application.bot.set_my_commands(commands)
    logger.info("Telegram bot commands registered")


def create_bot_application() -> Optional[Application]:
    """Create and configure the Telegram bot application."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set - Telegram bot disabled")
        return None

    logger.info("Initializing Telegram bot...")

    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Track chats globally so scheduled alerts can target active users.
    application.add_handler(MessageHandler(filters.ALL, track_chat_id), group=-1)

    # Register command handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("ajuda", cmd_ajuda))
    application.add_handler(CommandHandler("help", cmd_ajuda))
    application.add_handler(CommandHandler("novo_contrato", cmd_novo_contrato))
    application.add_handler(CommandHandler("reconectar", cmd_reconectar))
    application.add_handler(CommandHandler("cancelar", cmd_cancelar))
    application.add_handler(CommandHandler("clientes", cmd_clientes))
    application.add_handler(CommandHandler("contratos", cmd_contratos))
    application.add_handler(CommandHandler("templates_contrato", cmd_templates_contrato))
    application.add_handler(CommandHandler("templatescontrato", cmd_templates_contrato))
    application.add_handler(CommandHandler("preview_contrato", cmd_preview_contrato))
    application.add_handler(CommandHandler("previewcontrato", cmd_preview_contrato))
    application.add_handler(CommandHandler("pdf_contrato", cmd_pdf_contrato))
    application.add_handler(CommandHandler("pdfcontrato", cmd_pdf_contrato))
    application.add_handler(CommandHandler("contratos_vencendo", cmd_contratos_vencendo))
    application.add_handler(CommandHandler("contratosvencendo", cmd_contratos_vencendo))
    application.add_handler(CommandHandler("vencimentos", cmd_contratos_vencendo))
    application.add_handler(CommandHandler("sync_assinaturas", cmd_sync_assinaturas))
    application.add_handler(CommandHandler("syncassinaturas", cmd_sync_assinaturas))
    application.add_handler(CommandHandler("dashboard", cmd_dashboard))
    application.add_handler(CommandHandler("inadimplencia", cmd_inadimplencia_ca))
    application.add_handler(CommandHandler("sincronizar", cmd_sincronizar))
    application.add_handler(CommandHandler("cobrar_email", cmd_cobrar_email))
    application.add_handler(CommandHandler("cobraremail", cmd_cobrar_email))
    application.add_handler(CommandHandler("resumo_cobranca", cmd_resumo_cobranca))
    application.add_handler(CommandHandler("resumocobranca", cmd_resumo_cobranca))
    if _is_whatsapp_phase_enabled():
        application.add_handler(CommandHandler("cobrar_whatsapp", cmd_cobrar_whatsapp))
        application.add_handler(CommandHandler("cobrar_whatsap", cmd_cobrar_whatsapp))
        application.add_handler(CommandHandler("cobrarwhatsapp", cmd_cobrar_whatsapp))
        application.add_handler(CommandHandler("cobrarwhatsap", cmd_cobrar_whatsapp))
        application.add_handler(CommandHandler("cobrar", cmd_cobrar_whatsapp))
        application.add_handler(CommandHandler("wa_bloqueados", cmd_whatsapp_bloqueados))
        application.add_handler(CommandHandler("wa_desbloquear", cmd_whatsapp_desbloquear))
    application.add_handler(CommandHandler("sync_financeiro", cmd_sync_financeiro))
    application.add_handler(CommandHandler("receber", cmd_receber))
    application.add_handler(CommandHandler("pagar", cmd_pagar))
    application.add_handler(CommandHandler("saldos", cmd_saldos))
    application.add_handler(CommandHandler("cfo", cmd_cfo))
    application.add_handler(CommandHandler("operacao_dia", cmd_operacao_dia))
    application.add_handler(CommandHandler("operacaodia", cmd_operacao_dia))
    application.add_handler(CommandHandler("operacao", cmd_operacao_dia))
    application.add_handler(CommandHandler("resumo_semanal", cmd_resumo_semanal))
    application.add_handler(CommandHandler("status", cmd_status))

    # Unknown command fallback (must be before free-text handler)
    application.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    # Register message handler (must be last - catches all plain text)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram bot configured with all handlers")
    return application


async def start_bot(application: Application):
    """Start the Telegram bot polling in the background."""
    try:
        await application.initialize()
        await setup_commands(application)
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("✅ Telegram bot started and polling for messages")
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
        raise


async def stop_bot(application: Application):
    """Stop the Telegram bot gracefully."""
    try:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Telegram bot stopped")
    except Exception as e:
        logger.error(f"Error stopping Telegram bot: {e}")
