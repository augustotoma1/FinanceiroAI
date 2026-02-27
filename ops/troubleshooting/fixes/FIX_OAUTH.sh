#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# FIX_OAUTH.sh — Adiciona HTTP Basic Auth nos métodos OAuth do v2
# ═══════════════════════════════════════════════════════════════
# O v1 usava auth=(client_id, client_secret) no httpx.post() para
# o endpoint https://auth.contaazul.com/oauth2/token (AWS Cognito).
# O v2 só manda no body — Cognito rejeita com invalid_grant.
#
# Este script corrige os dois métodos: refresh_token e exchange_code.
# Também corrige o scope do get_authorization_url para incluir os
# scopes do Cognito que o v1 usava.
# ═══════════════════════════════════════════════════════════════

set -e
SERVICE_FILE="/opt/agent-financeiro-aisatec/app/services/conta_azul_service.py"

echo "═══════════════════════════════════════════════════════"
echo " FIX OAUTH — HTTP Basic Auth para Conta Azul v2"
echo "═══════════════════════════════════════════════════════"

# Backup
cp "$SERVICE_FILE" "${SERVICE_FILE}.bak_pre_oauth_fix"
echo "Backup: ${SERVICE_FILE}.bak_pre_oauth_fix"

# -----------------------------------------------------------
# Fix 1: refresh_token — adicionar auth=(client_id, client_secret)
# -----------------------------------------------------------
echo ""
echo "--- Fix 1: refresh_token ---"

python3 << 'PYEOF'
import re

path = "/opt/agent-financeiro-aisatec/app/services/conta_azul_service.py"
with open(path, "r") as f:
    content = f.read()

# Pattern: the POST call in refresh_token method
# We need to add auth=(client_id, client_secret) to the httpx.post call
# The current code has:
#   response = await client.post(
#       AUTH_URL,
#       data={...},
#       headers={...}
#   )
# Inside the refresh_token method.

# We'll use a targeted replacement for the refresh_token method's POST call
old_refresh = '''    async def refresh_token(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str
    ) -> Optional[Dict]:
        """
        Refresh OAuth 2.0 access token.

        Returns: {access_token, refresh_token, expires_in, token_type}
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    AUTH_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )'''

new_refresh = '''    async def refresh_token(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str
    ) -> Optional[Dict]:
        """
        Refresh OAuth 2.0 access token.

        Returns: {access_token, refresh_token, expires_in, token_type}
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    AUTH_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    auth=(client_id, client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )'''

if old_refresh in content:
    content = content.replace(old_refresh, new_refresh)
    print("OK: refresh_token patched with HTTP Basic Auth")
elif "auth=(client_id, client_secret)" in content.split("async def refresh_token")[1].split("async def exchange_code")[0] if "async def refresh_token" in content else False:
    print("SKIP: refresh_token already has Basic Auth")
else:
    # Try a more flexible approach
    # Find the refresh_token method and add auth param
    pattern = r'(async def refresh_token\b.*?await client\.post\(\s*AUTH_URL,\s*data=\{[^}]*\},)\s*(headers=)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        # Check if auth= already present between data and headers
        segment = content[match.start():match.end()]
        if 'auth=' not in segment:
            content = content[:match.end()-len('headers=')] + \
                      '                    auth=(client_id, client_secret),\n                    headers=' + \
                      content[match.end():]
            print("OK: refresh_token patched (flexible match)")
        else:
            print("SKIP: refresh_token already patched")
    else:
        print("WARN: Could not find refresh_token POST pattern - trying line-by-line")
        lines = content.split('\n')
        in_refresh = False
        patched = False
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            if 'async def refresh_token(' in line:
                in_refresh = True
            if in_refresh and 'async def exchange_code(' in line:
                in_refresh = False
            if in_refresh and '"client_secret": client_secret,' in line and not patched:
                # Remove client_id and client_secret from data dict
                # Actually, for Basic Auth, we should remove them from body
                # and add auth= param
                pass
            if in_refresh and 'headers={"Content-Type"' in line and 'auth=' not in lines[i-1] if i > 0 else True:
                # Insert auth= before headers=
                indent = '                    '
                new_lines.insert(-1, indent + 'auth=(client_id, client_secret),')
                patched = True
                print("OK: refresh_token patched (line-by-line)")
        if patched:
            content = '\n'.join(new_lines)
        else:
            print("ERROR: Could not patch refresh_token")

with open(path, "w") as f:
    f.write(content)
PYEOF

# -----------------------------------------------------------
# Fix 2: exchange_code — adicionar auth=(client_id, client_secret)
# -----------------------------------------------------------
echo ""
echo "--- Fix 2: exchange_code ---"

python3 << 'PYEOF'
path = "/opt/agent-financeiro-aisatec/app/services/conta_azul_service.py"
with open(path, "r") as f:
    content = f.read()

old_exchange = '''    async def exchange_code(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str
    ) -> Optional[Dict]:
        """
        Exchange authorization code for access token.

        Returns: {access_token, refresh_token, expires_in, token_type}
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    AUTH_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )'''

new_exchange = '''    async def exchange_code(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str
    ) -> Optional[Dict]:
        """
        Exchange authorization code for access token.

        Returns: {access_token, refresh_token, expires_in, token_type}
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    AUTH_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    auth=(client_id, client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )'''

if old_exchange in content:
    content = content.replace(old_exchange, new_exchange)
    print("OK: exchange_code patched with HTTP Basic Auth")
else:
    # Check if already patched
    if "async def exchange_code" in content:
        exchange_section = content.split("async def exchange_code")[1].split("\n\n    async def ")[0] if "async def exchange_code" in content else ""
        if "auth=(client_id, client_secret)" in exchange_section:
            print("SKIP: exchange_code already has Basic Auth")
        else:
            print("WARN: exchange_code pattern didn't match exactly - trying flexible")
            # Try inserting auth= before headers= in exchange_code
            lines = content.split('\n')
            in_exchange = False
            patched = False
            new_lines = []
            for i, line in enumerate(lines):
                new_lines.append(line)
                if 'async def exchange_code(' in line:
                    in_exchange = True
                if in_exchange and i > 0 and ('async def sync_clientes' in line or '# 13.' in line):
                    in_exchange = False
                if in_exchange and 'headers={"Content-Type"' in line and not patched:
                    prev = new_lines[-2] if len(new_lines) >= 2 else ""
                    if 'auth=' not in prev:
                        indent = '                    '
                        new_lines.insert(-1, indent + 'auth=(client_id, client_secret),')
                        patched = True
                        print("OK: exchange_code patched (line-by-line)")
            if patched:
                content = '\n'.join(new_lines)
            else:
                print("ERROR: Could not patch exchange_code")
    else:
        print("ERROR: exchange_code method not found!")

with open(path, "w") as f:
    f.write(content)
PYEOF

# -----------------------------------------------------------
# Fix 3: Atualizar scope do get_authorization_url wrapper
# -----------------------------------------------------------
echo ""
echo "--- Fix 3: Scope do get_authorization_url ---"

python3 << 'PYEOF'
path = "/opt/agent-financeiro-aisatec/app/services/conta_azul_service.py"
with open(path, "r") as f:
    content = f.read()

# O wrapper atual usa scope='openid', mas v1 usava scopes extras do Cognito
old_scope = "'scope': 'openid',"
new_scope = "'scope': 'openid profile aws.cognito.signin.user.admin',"

if old_scope in content:
    content = content.replace(old_scope, new_scope)
    print("OK: get_authorization_url scope updated to include Cognito scopes")
elif new_scope in content:
    print("SKIP: scope already includes Cognito scopes")
else:
    print("WARN: scope pattern not found (may need manual check)")

with open(path, "w") as f:
    f.write(content)
PYEOF

# -----------------------------------------------------------
# Fix 4: Remover client_id/client_secret do body do refresh_token
#         (com Basic Auth, não devem ir no body)
# -----------------------------------------------------------
echo ""
echo "--- Fix 4: Limpar body do refresh_token ---"

python3 << 'PYEOF'
path = "/opt/agent-financeiro-aisatec/app/services/conta_azul_service.py"
with open(path, "r") as f:
    content = f.read()

# No refresh_token, se Basic Auth está sendo usado, podemos remover
# client_id e client_secret do data dict (já vão no header Authorization)
# Verificar se o fix 1 já removeu
if 'auth=(client_id, client_secret)' in content:
    # Verificar se client_id/client_secret ainda estão no data do refresh_token
    sections = content.split('async def refresh_token(')
    if len(sections) > 1:
        method_body = sections[1].split('async def exchange_code(')[0]
        if '"client_id": client_id,' in method_body and '"client_secret": client_secret,' in method_body:
            # Remove from refresh_token data dict
            old_data = '''"grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,'''
            new_data = '''"grant_type": "refresh_token",
                        "refresh_token": refresh_token,'''
            if old_data in content:
                content = content.replace(old_data, new_data, 1)
                print("OK: Removed client_id/client_secret from refresh_token body")
            else:
                print("SKIP: refresh_token body already clean or different format")
        else:
            print("SKIP: refresh_token body already clean")

    # Same for exchange_code
    sections2 = content.split('async def exchange_code(')
    if len(sections2) > 1:
        method_body2 = sections2[1].split('async def sync_clientes')[0] if 'async def sync_clientes' in sections2[1] else sections2[1][:500]
        if '"client_id": client_id,' in method_body2 and '"client_secret": client_secret,' in method_body2:
            old_data2 = '''"grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": client_id,
                        "client_secret": client_secret,'''
            new_data2 = '''"grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,'''
            if old_data2 in content:
                content = content.replace(old_data2, new_data2, 1)
                print("OK: Removed client_id/client_secret from exchange_code body")
            else:
                print("SKIP: exchange_code body already clean or different format")
        else:
            print("SKIP: exchange_code body already clean")
else:
    print("WARN: Basic Auth not found - Fix 1/2 may have failed")

with open(path, "w") as f:
    f.write(content)
PYEOF

# -----------------------------------------------------------
# Verificação
# -----------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════"
echo " VERIFICAÇÃO"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "-- refresh_token method (auth= check) --"
grep -n "auth=(client_id" "$SERVICE_FILE" || echo "FALHA: auth= não encontrado!"

echo ""
echo "-- Data dicts should NOT have client_id/client_secret --"
python3 << 'PYEOF'
with open("/opt/agent-financeiro-aisatec/app/services/conta_azul_service.py") as f:
    content = f.read()

# Check refresh_token
rt = content.split("async def refresh_token(")[1].split("async def exchange_code(")[0]
if '"client_id"' in rt or '"client_secret"' in rt:
    print("WARN: refresh_token still has client credentials in body")
else:
    print("OK: refresh_token body is clean (credentials only in Basic Auth)")

# Check exchange_code
ec = content.split("async def exchange_code(")[1].split("# 13.")[0] if "# 13." in content.split("async def exchange_code(")[1] else content.split("async def exchange_code(")[1][:500]
if '"client_id"' in ec or '"client_secret"' in ec:
    print("WARN: exchange_code still has client credentials in body")
else:
    print("OK: exchange_code body is clean (credentials only in Basic Auth)")
PYEOF

echo ""
echo "-- Scope check --"
grep -n "aws.cognito" "$SERVICE_FILE" || echo "INFO: Cognito scopes not in file (may be OK)"

# -----------------------------------------------------------
# Restart
# -----------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════"
echo " RESTART SERVICE"
echo "═══════════════════════════════════════════════════════"
systemctl restart agent-financeiro
sleep 3
systemctl status agent-financeiro --no-pager -l | head -20

echo ""
echo "═══════════════════════════════════════════════════════"
echo " LOGS RECENTES"
echo "═══════════════════════════════════════════════════════"
journalctl -u agent-financeiro --no-pager -n 15

echo ""
echo "═══════════════════════════════════════════════════════"
echo " PRÓXIMO PASSO"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Acesse para re-autorizar:"
echo "  https://api.satec.digital/api/auth/conta-azul/authorize"
echo ""
echo "Depois teste no Telegram:"
echo "  /fluxo"
echo ""
