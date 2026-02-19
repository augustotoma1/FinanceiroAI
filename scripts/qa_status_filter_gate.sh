#!/usr/bin/env bash
# Quality gate for API filter contract regression (`status_filter` vs legacy `status`)

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

echo "[QA Gate] Validando contrato status_filter..."
python scripts/check_status_filter_contract.py
pytest -q -o addopts='' tests/test_api/test_status_filter_contract.py
echo "[QA Gate] OK: contrato status_filter validado."
