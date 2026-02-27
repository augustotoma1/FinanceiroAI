#!/bin/bash
# =============================================================
# PATCH: Fix invalid_grant handling + chat livre loop
# Deploy: rsync dos 4 arquivos alterados + restart serviço
#
# Arquivos alterados:
#   1. app/services/conta_azul_service.py
#      - Nova exceção ContaAzulInvalidGrantError
#      - Remoção de auth dupla (body + basic auth) no refresh
#      - Detecção explícita de invalid_grant
#
#   2. app/services/telegram_bot.py
#      - _get_conta_azul_token: trata invalid_grant com mensagem clara
#      - cmd_status: não sugere mais /sincronizar para token expirado
#      - cmd_sincronizar: detecta invalid_grant no erro e orienta reconexão
#      - Chat livre: system prompt impede Claude de fingir acesso a dados
#
#   3. app/background/sync_clients.py
#      - Import + catch de ContaAzulInvalidGrantError
#
#   4. app/background/sync_financial.py
#      - Import + catch de ContaAzulInvalidGrantError
# =============================================================

set -e

VPS_HOST="root@76.13.166.36"
APP_DIR="/opt/agent-financeiro-aisatec"

echo "========================================="
echo "  PATCH: invalid_grant + chat livre fix"
echo "========================================="

# --- 1. Rsync apenas os 4 arquivos modificados ---
echo "[1/3] Enviando arquivos para o VPS..."

rsync -avz \
  app/services/conta_azul_service.py \
  "${VPS_HOST}:${APP_DIR}/app/services/conta_azul_service.py"

rsync -avz \
  app/services/telegram_bot.py \
  "${VPS_HOST}:${APP_DIR}/app/services/telegram_bot.py"

rsync -avz \
  app/background/sync_clients.py \
  "${VPS_HOST}:${APP_DIR}/app/background/sync_clients.py"

rsync -avz \
  app/background/sync_financial.py \
  "${VPS_HOST}:${APP_DIR}/app/background/sync_financial.py"

echo "✅ Arquivos enviados"

# --- 2. Restart do serviço ---
echo "[2/3] Reiniciando serviço..."
ssh "${VPS_HOST}" "systemctl restart agent-financeiro"
echo "✅ Serviço reiniciado"

# --- 3. Verificação ---
echo "[3/3] Verificando saúde..."
sleep 3
ssh "${VPS_HOST}" "systemctl is-active agent-financeiro && echo '✅ Serviço ativo' || echo '❌ Serviço falhou'"
ssh "${VPS_HOST}" "journalctl -u agent-financeiro --no-pager -n 5"

echo ""
echo "========================================="
echo "  PATCH aplicado!"
echo "========================================="
echo ""
echo "  PRÓXIMO PASSO OBRIGATÓRIO:"
echo "  Reautorizar OAuth do Conta Azul:"
echo "  👉 https://api.satec.digital/api/auth/conta-azul/authorize"
echo ""
echo "  Depois confirmar com:"
echo "  👉 https://api.satec.digital/api/auth/conta-azul/status"
echo ""
echo "  No bot, testar:"
echo "  /status → deve mostrar Token ativo"
echo "  /saldos /receber /pagar /sincronizar"
echo ""
