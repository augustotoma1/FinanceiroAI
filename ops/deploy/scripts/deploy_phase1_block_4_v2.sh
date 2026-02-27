#!/bin/bash
# Block 4: Post-deploy - Apply patches and restart

cd /opt/agent-financeiro

# Ensure httpx is installed (needed by new service)
pip install httpx --break-system-packages -q 2>/dev/null

# Verify files exist
echo "Verificando arquivos..."
ls -la app/services/conta_azul_service.py
ls -la app/config.py
ls -la patch_novos_comandos.py

echo ""
echo "=== IMPORTANTE ==="
echo "Os novos comandos do patch_novos_comandos.py precisam ser"
echo "inseridos no telegram_bot_v2.py manualmente ou via proximo deploy."
echo ""
echo "Novos comandos disponiveis apos merge:"
echo "  /fluxo - Fluxo de caixa e projecoes"
echo "  /dre - Estrutura DRE"
echo "  /categorias - Categorias financeiras"
echo "  /centros - Centros de custo"
echo "  /vendas - Vendas recentes"
echo "  /resumo - Resumo financeiro completo"
echo ""

# Restart service
sudo systemctl restart agent-financeiro
sleep 3
sudo systemctl status agent-financeiro --no-pager -l
echo ""
echo "Deploy Phase 1 concluido!"
