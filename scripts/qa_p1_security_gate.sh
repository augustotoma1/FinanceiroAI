#!/usr/bin/env bash
# P1 security gate for critical API/auth/OAuth/logging regressions.

set -euo pipefail

PROJECT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${PROJECT_DIR}"

if [[ "${QA_SKIP_LOCAL_VENV:-0}" != "1" && -x "venv/bin/python" && -f "venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

if ! command -v pytest >/dev/null 2>&1; then
  echo "ERRO: pytest não encontrado no ambiente atual."
  echo "Instale dependências e rode novamente."
  exit 1
fi

echo "[QA Gate] Validando P1 (segurança/autorização/OAuth/logs)..."
pytest -q -o addopts='' \
  tests/test_api/test_endpoints.py::TestApiSecurity::test_critical_routes_require_api_key \
  tests/test_api/test_endpoints.py::TestApiSecurity::test_critical_routes_reject_invalid_api_key \
  tests/test_api/test_endpoints.py::TestAuthEndpoints::test_callback_state_token_is_one_time_use \
  tests/test_api/test_endpoints.py::TestAuthEndpoints::test_autentique_webhook_rejects_invalid_secret \
  tests/test_api/test_endpoints.py::TestAuthEndpoints::test_autentique_webhook_accepts_valid_secret_bearer \
  tests/test_api/test_endpoints.py::TestAuthEndpoints::test_status_requires_valid_api_key \
  tests/test_services/test_conta_azul.py::TestSanitizeErrorDetail::test_redacts_json_token_fields \
  tests/test_services/test_conta_azul.py::TestSanitizeErrorDetail::test_redacts_bearer_and_query_tokens
echo "[QA Gate] OK: P1 segurança validado."
