#!/usr/bin/env python3
"""
Fix timezone comparison error across all Python files.
Replaces datetime.utcnow() with datetime.now(timezone.utc) and adds timezone import.
Run this script on the VPS: python3 /opt/agent-financeiro-aisatec/fix_timezone.py
"""
import re
import os

BASE_DIR = "/opt/agent-financeiro-aisatec"

files_to_fix = [
    "app/models/integration_token.py",
    "app/background/sync_clients.py",
    "app/api/auth.py",
    "app/services/conta_azul_service.py",
]

total_changes = 0

for rel_path in files_to_fix:
    filepath = os.path.join(BASE_DIR, rel_path)
    if not os.path.exists(filepath):
        print(f"SKIP: {rel_path} (arquivo nao encontrado)")
        continue

    with open(filepath, "r") as f:
        content = f.read()

    original = content
    changes = 0

    # 1. Add timezone to datetime import if not already there
    # Match "from datetime import datetime" or "from datetime import datetime, timedelta"
    if "timezone" not in content:
        # Pattern: from datetime import X, Y (add timezone)
        pattern = r"(from datetime import\s+)(datetime(?:,\s*\w+)*)"
        match = re.search(pattern, content)
        if match:
            old_import = match.group(0)
            new_import = old_import + ", timezone"
            content = content.replace(old_import, new_import, 1)
            changes += 1
            print(f"  + Adicionou 'timezone' ao import em {rel_path}")

    # 2. Replace datetime.utcnow() with datetime.now(timezone.utc)
    count = content.count("datetime.utcnow()")
    if count > 0:
        content = content.replace("datetime.utcnow()", "datetime.now(timezone.utc)")
        changes += count
        print(f"  + Substituiu {count}x datetime.utcnow() em {rel_path}")

    # 3. Special fix for integration_token.py is_expired method
    if "integration_token.py" in rel_path:
        # Replace the is_expired comparison to handle both aware and naive datetimes
        old_is_expired = """        buffer = timedelta(minutes=buffer_minutes)
        return datetime.now(timezone.utc) >= (self.expires_at - buffer)"""

        new_is_expired = """        buffer = timedelta(minutes=buffer_minutes)
        now = datetime.now(timezone.utc)
        # Ensure expires_at is timezone-aware for comparison
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now >= (expires - buffer)"""

        if old_is_expired in content:
            content = content.replace(old_is_expired, new_is_expired)
            changes += 1
            print(f"  + Corrigiu is_expired() com tratamento timezone-aware em {rel_path}")
        elif "expires.tzinfo is None" in content:
            print(f"  = is_expired() ja esta corrigido em {rel_path}")
        else:
            # Try the original version that hasn't been partially fixed
            old_orig = """        buffer = timedelta(minutes=buffer_minutes)
        return datetime.utcnow() >= (self.expires_at - buffer)"""
            if old_orig in content:
                content = content.replace(old_orig, new_is_expired)
                changes += 1
                print(f"  + Corrigiu is_expired() original em {rel_path}")

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        total_changes += changes
        print(f"  => {rel_path}: {changes} alteracoes salvas")
    else:
        print(f"  = {rel_path}: nenhuma alteracao necessaria")

print(f"\nTotal: {total_changes} alteracoes em {len(files_to_fix)} arquivos")
print("\nAgora reinicie o servico:")
print("  sudo systemctl restart agent-financeiro")
