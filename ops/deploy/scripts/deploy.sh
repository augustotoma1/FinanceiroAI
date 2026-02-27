#!/bin/bash
# =============================================================
# Deploy Script - Agent Financeiro AISATEC
# Deploys FastAPI app to Hostinger VPS with Nginx + SSL
# =============================================================

set -e

echo "========================================="
echo "  Deploy - Agent Financeiro AISATEC"
echo "========================================="

# --- 1. System Update ---
echo "[1/8] Atualizando sistema..."
apt update && apt upgrade -y

# --- 2. Install Dependencies ---
echo "[2/8] Instalando dependências..."
apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx certbot python3-certbot-nginx git curl

# --- 3. Setup PostgreSQL ---
echo "[3/8] Configurando PostgreSQL..."
sudo -u postgres psql -c "CREATE USER agentfinanceiro WITH PASSWORD 'Satec2026!';" 2>/dev/null || echo "User já existe"
sudo -u postgres psql -c "CREATE DATABASE financial_automation OWNER agentfinanceiro;" 2>/dev/null || echo "Database já existe"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE financial_automation TO agentfinanceiro;"

# --- 4. Setup Application ---
echo "[4/8] Configurando aplicação..."
APP_DIR="/opt/agent-financeiro-aisatec"
mkdir -p $APP_DIR

# Copy files (will be done via rsync from Mac)
if [ ! -f "$APP_DIR/app/main.py" ]; then
    echo "AVISO: Arquivos da aplicação não encontrados em $APP_DIR"
    echo "Execute no Mac: rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='.git' ./ root@76.13.166.36:/opt/agent-financeiro-aisatec/"
    echo "Depois execute este script novamente."
    exit 1
fi

# Create virtual environment
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Optional API contract quality gates (enabled by default)
if [ "${SKIP_QA_GATES:-0}" != "1" ]; then
    echo "[4.1/8] Executando quality gate da API (status_filter)..."
    if [ -x "$APP_DIR/scripts/qa_status_filter_gate.sh" ]; then
        "$APP_DIR/scripts/qa_status_filter_gate.sh" "$APP_DIR"
    else
        pytest -q -o addopts='' tests/test_api/test_endpoints.py -k 'status_filter or legacy_status or guardrails or openapi_uses_status_filter'
    fi

    echo "[4.2/8] Executando quality gate P1 de segurança..."
    if [ -x "$APP_DIR/scripts/qa_p1_security_gate.sh" ]; then
        "$APP_DIR/scripts/qa_p1_security_gate.sh" "$APP_DIR"
    else
        pytest -q -o addopts='' \
          tests/test_api/test_endpoints.py::TestApiSecurity::test_critical_routes_require_api_key \
          tests/test_api/test_endpoints.py::TestApiSecurity::test_critical_routes_reject_invalid_api_key \
          tests/test_api/test_endpoints.py::TestAuthEndpoints::test_callback_state_token_is_one_time_use \
          tests/test_api/test_endpoints.py::TestAuthEndpoints::test_autentique_webhook_rejects_invalid_secret \
          tests/test_api/test_endpoints.py::TestAuthEndpoints::test_autentique_webhook_accepts_valid_secret_bearer \
          tests/test_api/test_endpoints.py::TestAuthEndpoints::test_status_requires_valid_api_key \
          tests/test_services/test_conta_azul.py::TestSanitizeErrorDetail::test_redacts_json_token_fields \
          tests/test_services/test_conta_azul.py::TestSanitizeErrorDetail::test_redacts_bearer_and_query_tokens
    fi
else
    echo "[4.1/8] SKIP_QA_GATES=1 -> quality gates ignorados."
fi

# Update DATABASE_URL in .env for VPS PostgreSQL
sed -i 's|DATABASE_URL=.*|DATABASE_URL=postgresql://agentfinanceiro:Satec2026!@localhost/financial_automation|' .env

# --- 5. Setup Systemd Service ---
echo "[5/8] Configurando serviço systemd..."
cat > /etc/systemd/system/agent-financeiro.service << 'EOF'
[Unit]
Description=Agent Financeiro AISATEC - FastAPI
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/agent-financeiro-aisatec
Environment=PATH=/opt/agent-financeiro-aisatec/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=/opt/agent-financeiro-aisatec/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable agent-financeiro
systemctl restart agent-financeiro

# --- 6. Setup Nginx ---
echo "[6/8] Configurando Nginx..."
cat > /etc/nginx/sites-available/agent-financeiro << 'EOF'
server {
    listen 80;
    server_name api.satec.digital;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }
}
EOF

ln -sf /etc/nginx/sites-available/agent-financeiro /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# --- 7. Setup SSL with Let's Encrypt ---
echo "[7/8] Configurando SSL..."
certbot --nginx -d api.satec.digital --non-interactive --agree-tos --email augustotoma@gmail.com --redirect

# --- 8. Initialize Database Tables ---
echo "[8/8] Inicializando banco de dados..."
cd $APP_DIR
source venv/bin/activate
python -c "
from app.database import engine, Base
Base.metadata.create_all(bind=engine)
print('Database tables created successfully')
" 2>/dev/null || echo "Tabelas já existem ou serão criadas na inicialização"

# Restart service to ensure everything is fresh
systemctl restart agent-financeiro

echo ""
echo "========================================="
echo "  Deploy concluído!"
echo "========================================="
echo ""
echo "  URL: https://api.satec.digital"
echo "  Health: https://api.satec.digital/health"
echo "  OAuth: https://api.satec.digital/api/auth/conta-azul/authorize"
echo ""
echo "  Comandos úteis:"
echo "    systemctl status agent-financeiro"
echo "    journalctl -u agent-financeiro -f"
echo ""
