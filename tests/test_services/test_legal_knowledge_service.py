"""Unit tests for legal knowledge grounding service."""

from __future__ import annotations

import json

from app.config import settings
from app.services.legal_knowledge_service import LegalKnowledgeService


def test_is_legal_query_detects_common_terms() -> None:
    service = LegalKnowledgeService()
    assert service.is_legal_query("Qual cláusula de rescisão devo usar no contrato?") is True
    assert service.is_legal_query("mostrar status dos clientes") is False


def test_search_returns_ranked_sources(tmp_path, monkeypatch) -> None:
    kb_path = tmp_path / "sources.json"
    kb_path.write_text(
        json.dumps(
            [
                {
                    "source_id": "cc",
                    "title": "Código Civil - Contratos",
                    "url": "https://example.org/cc",
                    "content": "Contrato exige boa-fe, validade do negócio e tratamento de inadimplemento.",
                },
                {
                    "source_id": "lgpd",
                    "title": "LGPD",
                    "url": "https://example.org/lgpd",
                    "content": "Dados pessoais exigem base legal e minimizacao de tratamento.",
                },
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "LEGAL_KNOWLEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "LEGAL_KNOWLEDGE_PATH", str(kb_path))
    monkeypatch.setattr(settings, "LEGAL_KNOWLEDGE_MAX_SNIPPETS", 2)
    monkeypatch.setattr(settings, "LEGAL_KNOWLEDGE_MIN_SCORE", 1)

    service = LegalKnowledgeService()
    result = service.search("boa-fe e cláusula de contrato")

    assert len(result.matches) >= 1
    assert result.matches[0]["source_id"] == "cc"


def test_build_prompt_block_without_evidence(tmp_path, monkeypatch) -> None:
    kb_path = tmp_path / "sources.json"
    kb_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(settings, "LEGAL_KNOWLEDGE_ENABLED", True)
    monkeypatch.setattr(settings, "LEGAL_KNOWLEDGE_PATH", str(kb_path))

    service = LegalKnowledgeService()
    payload = service.build_prompt_block("tema jurídico altamente específico")

    assert payload["has_evidence"] is False
    assert payload["sources"] == []
