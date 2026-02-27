#!/bin/bash
# Diagnóstico: Por que os comandos do Telegram não respondem?
echo "========================================="
echo "  DIAGNÓSTICO DO BOT TELEGRAM"
echo "========================================="
echo ""

# 1. Verificar serviço
echo "--- 1. SERVIÇO SYSTEMD ---"
cat /etc/systemd/system/agent-financeiro.service 2>/dev/null || echo "Arquivo de serviço não encontrado!"
echo ""

# 2. Verificar diretórios
echo "--- 2. DIRETÓRIOS ---"
echo ">> /opt/agent-financeiro:"
ls -la /opt/agent-financeiro 2>/dev/null | head -5 || echo "NÃO EXISTE"
echo ""
echo ">> /opt/agent-financeiro-aisatec:"
ls -la /opt/agent-financeiro-aisatec 2>/dev/null | head -5 || echo "NÃO EXISTE"
echo ""

# 3. Verificar se é symlink
echo "--- 3. SYMLINK CHECK ---"
file /opt/agent-financeiro 2>/dev/null
file /opt/agent-financeiro-aisatec 2>/dev/null
echo ""

# 4. Verificar merge no diretório do deploy
echo "--- 4. MERGE NO /opt/agent-financeiro/ ---"
if [ -f /opt/agent-financeiro/telegram_bot_v2.py ]; then
    echo "Arquivo existe! Tamanho:"
    wc -l /opt/agent-financeiro/telegram_bot_v2.py
    echo "Contém cmd_fluxo?"
    grep -c "cmd_fluxo" /opt/agent-financeiro/telegram_bot_v2.py
    grep -c "cmd_resumo" /opt/agent-financeiro/telegram_bot_v2.py
else
    echo "NÃO EXISTE em /opt/agent-financeiro/"
fi
echo ""

# 5. Verificar merge no diretório aisatec
echo "--- 5. MERGE NO /opt/agent-financeiro-aisatec/ ---"
if [ -f /opt/agent-financeiro-aisatec/telegram_bot_v2.py ]; then
    echo "Arquivo existe! Tamanho:"
    wc -l /opt/agent-financeiro-aisatec/telegram_bot_v2.py
    echo "Contém cmd_fluxo?"
    grep -c "cmd_fluxo" /opt/agent-financeiro-aisatec/telegram_bot_v2.py
    grep -c "cmd_resumo" /opt/agent-financeiro-aisatec/telegram_bot_v2.py
else
    echo "NÃO EXISTE em /opt/agent-financeiro-aisatec/"
fi
echo ""

# 6. De onde o main.py importa o bot?
echo "--- 6. IMPORTS DO MAIN.PY ---"
for dir in /opt/agent-financeiro /opt/agent-financeiro-aisatec; do
    if [ -f "$dir/app/main.py" ]; then
        echo ">> $dir/app/main.py:"
        grep -n "telegram_bot\|import.*bot" "$dir/app/main.py" | head -10
        echo ""
    fi
done

# 7. Working directory do processo
echo "--- 7. PROCESSO RODANDO ---"
PID=$(pgrep -f "uvicorn app.main:app" | head -1)
if [ -n "$PID" ]; then
    echo "PID: $PID"
    echo "CWD: $(readlink -f /proc/$PID/cwd)"
    echo "CMD: $(cat /proc/$PID/cmdline | tr '\0' ' ')"
else
    echo "Processo não encontrado!"
fi
echo ""

# 8. Últimos erros
echo "--- 8. ÚLTIMOS ERROS NO LOG ---"
journalctl -u agent-financeiro --since "1 hour ago" --no-pager | grep -i "error\|exception\|traceback\|import" | tail -20
echo ""

echo "========================================="
echo "  FIM DO DIAGNÓSTICO"
echo "========================================="
