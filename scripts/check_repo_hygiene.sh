#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Repo hygiene check =="
echo "Repo: $ROOT_DIR"

fail=0

print_fail_with_sample() {
  local label="$1"
  local result="$2"
  local total
  total="$(printf "%s\n" "$result" | sed '/^$/d' | wc -l | tr -d ' ')"
  echo "[FAIL] $label (total=$total)"
  printf "%s\n" "$result" | sed '/^$/d' | awk 'NR<=40'
  if [[ "$total" -gt 40 ]]; then
    echo "... (truncated)"
  fi
  fail=1
}

check_tracked_exact() {
  local label="$1"
  local path="$2"
  local result
  result="$(git ls-files "$path" || true)"
  if [[ -n "$result" ]]; then
    print_fail_with_sample "$label" "$result"
  else
    echo "[OK] $label"
  fi
}

check_tracked_regex() {
  local label="$1"
  local regex="$2"
  local result
  result="$(git ls-files | rg -N "$regex" || true)"
  if [[ -n "$result" ]]; then
    print_fail_with_sample "$label" "$result"
  else
    echo "[OK] $label"
  fi
}

# Tracked file checks (must not be versioned)
check_tracked_exact "Tracked local env files" ".env"
key_result="$(git ls-files | rg -N '\.(pem|key|p12|pfx)$' | rg -N -v '^venv/' || true)"
if [[ -n "$key_result" ]]; then
  print_fail_with_sample "Tracked private keys/certs (outside venv)" "$key_result"
else
  echo "[OK] Tracked private keys/certs (outside venv)"
fi
check_tracked_regex "Tracked virtualenv files" '^venv/'
cache_result="$(git ls-files | rg -N '__pycache__/' | rg -N -v '^venv/' || true)"
if [[ -n "$cache_result" ]]; then
  print_fail_with_sample "Tracked Python cache files (outside venv)" "$cache_result"
else
  echo "[OK] Tracked Python cache files (outside venv)"
fi

# Working tree warning checks (local junk should be ignored)
dirty="$(git status --porcelain || true)"
if [[ -n "$dirty" ]]; then
  echo "[WARN] Working tree has pending changes."
  echo "$dirty" | awk 'NR<=40'
else
  echo "[OK] Working tree clean."
fi

if [[ "$fail" -ne 0 ]]; then
  echo "Hygiene check FAILED."
  exit 1
fi

echo "Hygiene check PASSED."
