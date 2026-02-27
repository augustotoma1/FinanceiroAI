#!/bin/bash
# =============================================================
# Script de Inicialização - Agent Financeiro AISATEC
# =============================================================
# Uso: ./start.sh
# =============================================================

set -e

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE} Agent Financeiro AISATEC - Startup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ---- 1. Verificar Python ----
echo -e "${YELLOW}[1/6] Verificando Python...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo -e "${GREEN}  ✓ $PYTHON_VERSION${NC}"
else
    echo -e "${RED}  ✗ Python 3 não encontrado. Instale com: brew install python3${NC}"
    exit 1
fi

# ---- 2. Verificar PostgreSQL ----
echo -e "${YELLOW}[2/6] Verificando PostgreSQL...${NC}"
if command -v psql &> /dev/null; then
    if pg_isready -q 2>/dev/null; then
        echo -e "${GREEN}  ✓ PostgreSQL está rodando${NC}"
    else
        echo -e "${RED}  ✗ PostgreSQL não está rodando. Inicie com: brew services start postgresql${NC}"
        exit 1
    fi
else
    echo -e "${RED}  ✗ psql não encontrado. Instale com: brew install postgresql${NC}"
    exit 1
fi

# ---- 3. Criar banco de dados se não existir ----
echo -e "${YELLOW}[3/6] Verificando banco de dados...${NC}"
if psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw financial_automation; then
    echo -e "${GREEN}  ✓ Banco 'financial_automation' já existe${NC}"
else
    echo -e "${YELLOW}  → Criando banco 'financial_automation'...${NC}"
    createdb financial_automation 2>/dev/null && \
        echo -e "${GREEN}  ✓ Banco criado com sucesso${NC}" || \
        echo -e "${RED}  ✗ Erro ao criar banco. Crie manualmente: createdb financial_automation${NC}"
fi

# ---- 4. Configurar ambiente virtual ----
echo -e "${YELLOW}[4/6] Configurando ambiente virtual...${NC}"
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}  → Criando venv...${NC}"
    python3 -m venv venv
fi
source venv/bin/activate
echo -e "${GREEN}  ✓ Ambiente virtual ativado${NC}"

# Instalar/atualizar dependências
echo -e "${YELLOW}  → Instalando dependências...${NC}"
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}  ✓ Dependências instaladas${NC}"

# ---- 5. Verificar .env ----
echo -e "${YELLOW}[5/6] Verificando configuração (.env)...${NC}"
if [ -f ".env" ]; then
    echo -e "${GREEN}  ✓ Arquivo .env encontrado${NC}"
else
    echo -e "${RED}  ✗ Arquivo .env não encontrado!${NC}"
    echo -e "${YELLOW}  → Copie o exemplo: cp .env.example .env${NC}"
    echo -e "${YELLOW}  → Edite com suas credenciais: nano .env${NC}"
    exit 1
fi

# ---- 6. Rodar migrações ----
echo -e "${YELLOW}[6/6] Rodando migrações do banco de dados...${NC}"
alembic upgrade head 2>&1 && \
    echo -e "${GREEN}  ✓ Migrações aplicadas com sucesso${NC}" || \
    echo -e "${YELLOW}  ⚠ Migrações podem já estar atualizadas${NC}"

# ---- Iniciar servidor ----
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} Sistema pronto! Iniciando servidor...${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}  API:     http://localhost:8000${NC}"
echo -e "${BLUE}  Docs:    http://localhost:8000/docs${NC}"
echo -e "${BLUE}  Health:  http://localhost:8000/health${NC}"
echo ""
echo -e "${YELLOW}  Pressione Ctrl+C para parar o servidor${NC}"
echo ""

# Iniciar FastAPI com uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
