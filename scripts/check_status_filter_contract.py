#!/usr/bin/env python3
"""
Static guardrail for API filter contract tests.

Fail when tests use legacy query param `status` (instead of `status_filter`)
for contracts/signatures listing endpoints.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, List, Tuple


TARGET_PREFIXES = ("/api/contracts/", "/api/signatures/")


def _iter_py_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if path.is_file():
            yield path


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_target_path(value: str | None) -> bool:
    if not value:
        return False
    return any(value.startswith(prefix) for prefix in TARGET_PREFIXES)


def _dict_has_status_key(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    for key in node.keys:
        key_value = _const_str(key)
        if key_value == "status":
            return True
    return False


def _check_source(path: Path, source: str) -> List[Tuple[int, str]]:
    findings: List[Tuple[int, str]] = []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        findings.append((exc.lineno or 1, f"syntax_error:{exc.msg}"))
        return findings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr.lower() != "get":
            continue

        endpoint = _const_str(node.args[0]) if node.args else None
        if _is_target_path(endpoint):
            for kw in node.keywords:
                if kw.arg == "params" and _dict_has_status_key(kw.value):
                    findings.append(
                        (
                            node.lineno,
                            "legacy_params_key_status",
                        )
                    )

        if endpoint and _is_target_path(endpoint):
            if "?status=" in endpoint or "&status=" in endpoint:
                findings.append((node.lineno, "legacy_query_status_literal"))

    return findings


def main() -> int:
    root = Path("tests")
    problems: List[Tuple[Path, int, str]] = []
    for py_file in _iter_py_files(root):
        content = py_file.read_text(encoding="utf-8")
        for line, reason in _check_source(py_file, content):
            problems.append((py_file, line, reason))

    if problems:
        print("ERRO: uso legado de `status` detectado em testes.")
        for file_path, line, reason in problems:
            print(f"- {file_path}:{line} ({reason})")
        print("Use `status_filter` para filtros de /api/contracts/ e /api/signatures/.")
        return 1

    print("OK: nenhum uso legado de `status` detectado para contratos/assinaturas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
