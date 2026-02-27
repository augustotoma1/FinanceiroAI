#!/bin/bash
# =============================================================
# AUTO-DEPLOY: invalid_grant fix + chat livre fix
#
# Uso: No Terminal do Mac, na pasta do projeto:
#   cd ~/agent-financeiro-aisatec   (ou onde estiver o projeto)
#   bash DEPLOY_PATCH_AUTO.sh
#
# Este script:
#   1. Envia os 4 arquivos corrigidos para o VPS via rsync/SSH
#   2. Reinicia o serviço agent-financeiro
#   3. Verifica se o serviço está rodando
#   4. Testa a API
# =============================================================

set -e

VPS_HOST="root@76.13.166.36"
APP_DIR="/opt/agent-financeiro-aisatec"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "  AUTO-DEPLOY: invalid_grant + chat fix"
echo "========================================="
echo ""
echo "Diretório do projeto: ${SCRIPT_DIR}"
echo ""

# --- 0. Check SSH ---
echo "[0/4] Testando conexão SSH..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "${VPS_HOST}" "echo 'SSH OK'" || {
    echo "❌ Falha na conexão SSH para ${VPS_HOST}"
    echo "   Verifique se você tem a chave SSH configurada."
    exit 1
}
echo "✅ SSH conectado"

# --- 1. Backup + Send files ---
echo ""
echo "[1/4] Criando backup e enviando arquivos..."

# Backup on VPS
ssh "${VPS_HOST}" "
    mkdir -p /tmp/backup_pre_patch
    cp -f ${APP_DIR}/app/services/conta_azul_service.py /tmp/backup_pre_patch/ 2>/dev/null || true
    cp -f ${APP_DIR}/app/services/telegram_bot.py /tmp/backup_pre_patch/ 2>/dev/null || true
    cp -f ${APP_DIR}/app/background/sync_clients.py /tmp/backup_pre_patch/ 2>/dev/null || true
    cp -f ${APP_DIR}/app/background/sync_financial.py /tmp/backup_pre_patch/ 2>/dev/null || true
    echo 'Backup salvo em /tmp/backup_pre_patch/'
"

# Rsync the 4 modified files
rsync -avz "${SCRIPT_DIR}/app/services/conta_azul_service.py" \
  "${VPS_HOST}:${APP_DIR}/app/services/conta_azul_service.py"

rsync -avz "${SCRIPT_DIR}/app/services/telegram_bot.py" \
  "${VPS_HOST}:${APP_DIR}/app/services/telegram_bot.py"

rsync -avz "${SCRIPT_DIR}/app/background/sync_clients.py" \
  "${VPS_HOST}:${APP_DIR}/app/background/sync_clients.py"

rsync -avz "${SCRIPT_DIR}/app/background/sync_financial.py" \
  "${VPS_HOST}:${APP_DIR}/app/background/sync_financial.py"

echo "✅ 4 arquivos enviados"

# --- 2. Restart service ---
echo ""
echo "[2/4] Reiniciando serviço..."
ssh "${VPS_HOST}" "systemctl restart agent-financeiro"
echo "✅ Serviço reiniciado"

# --- 3. Verify service ---
echo ""
echo "[3/4] Verificando saúde do serviço..."
sleep 4
ssh "${VPS_HOST}" "
    if systemctl is-active --quiet agent-financeiro; then
        echo '✅ Serviço ATIVO'
        journalctl -u agent-financeiro --no-pager -n 5
    else
        echo '❌ Serviço FALHOU — logs:'
        journalctl -u agent-financeiro --no-pager -n 20
        exit 1
    fi
"

# --- 4. Health check ---
echo ""
echo "[4/4] Testando API..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://api.satec.digital/health 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ API respondendo (HTTP 200)"
else
    echo "⚠️  API retornou HTTP ${HTTP_STATUS} (pode levar uns segundos para subir)"
fi

echo ""
echo "========================================="
echo "  PATCH APLICADO COM SUCESSO!"
echo "========================================="
echo ""
echo "  Arquivos atualizados:"
echo "    ✓ app/services/conta_azul_service.py"
echo "    ✓ app/services/telegram_bot.py"
echo "    ✓ app/background/sync_clients.py"
echo "    ✓ app/background/sync_financial.py"
echo ""
echo "  PRÓXIMO PASSO OBRIGATÓRIO:"
echo "  Reautorizar OAuth do Conta Azul:"
echo "  👉 https://api.satec.digital/api/auth/conta-azul/authorize"
echo ""
echo "  Depois confirmar com:"
echo "  👉 https://api.satec.digital/api/auth/conta-azul/status"
echo ""
echo "  No bot Telegram, testar:"
echo "    /status → deve mostrar Token ativo"
echo "    /saldos /receber /pagar /sincronizar"
echo ""
