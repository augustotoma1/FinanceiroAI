#!/usr/bin/env python3
"""
Validate OpenAPI contract for status filtering.

Checks that:
- /api/contracts/ GET exposes `status_filter` and not `status`
- /api/signatures/ GET exposes `status_filter` and not `status`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_env() -> None:
    os.environ.setdefault("API_SECRET_KEY", "test-secret-key-for-openapi-check")
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
    os.environ.setdefault("CONTA_AZUL_CLIENT_ID", "test-client-id")
    os.environ.setdefault("CONTA_AZUL_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault(
        "CONTA_AZUL_REDIRECT_URI",
        "http://localhost:8000/api/auth/conta-azul/callback",
    )
    os.environ.setdefault("AUTENTIQUE_API_KEY", "test-autentique-key")
    os.environ.setdefault("TESTING", "1")


def _param_names(schema: dict, path: str) -> set[str]:
    params = schema.get("paths", {}).get(path, {}).get("get", {}).get("parameters", [])
    return {str(item.get("name")) for item in params}


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    _bootstrap_env()
    from app.main import app

    schema = app.openapi()
    contracts = _param_names(schema, "/api/contracts/")
    signatures = _param_names(schema, "/api/signatures/")

    errors: list[str] = []
    if "status_filter" not in contracts:
        errors.append("contracts_missing_status_filter")
    if "status" in contracts:
        errors.append("contracts_exposes_legacy_status")
    if "status_filter" not in signatures:
        errors.append("signatures_missing_status_filter")
    if "status" in signatures:
        errors.append("signatures_exposes_legacy_status")

    if errors:
        print("ERRO: contrato OpenAPI status_filter inválido.")
        for err in errors:
            print(f"- {err}")
        return 1

    print("OK: OpenAPI expõe status_filter (sem status legado) para contratos/assinaturas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
