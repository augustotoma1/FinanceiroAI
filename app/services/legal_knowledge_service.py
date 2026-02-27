"""
Legal Knowledge Service

Provides deterministic retrieval over a curated local legal knowledge base
used to ground contract/legal guidance and reduce hallucinations.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LegalSource:
    source_id: str
    title: str
    url: str
    content: str


@dataclass
class LegalSearchResult:
    query: str
    matches: List[Dict[str, Any]]


_STOPWORDS = {
    "a", "ao", "aos", "as", "de", "do", "dos", "da", "das", "e", "em", "na", "no",
    "nos", "nas", "por", "para", "com", "sem", "sob", "que", "se", "ou", "como", "um",
    "uma", "uns", "umas", "o", "os", "é", "ser", "sua", "seu", "suas", "seus", "nao",
    "não", "mais", "menos", "muito", "muita", "muitos", "muitas", "ja", "já", "ate", "até",
}

_LEGAL_HINTS = {
    "contrato", "contratual", "clausula", "cláusula", "rescisao", "rescisão", "inadimplencia",
    "inadimplência", "multa", "penalidade", "lei", "legal", "juridico", "jurídico", "jurisprudencia",
    "jurisprudência", "codigo civil", "código civil", "lgpd", "dados pessoais", "licitacao",
    "licitação", "administrativo", "assinatura eletronica", "assinatura eletrônica", "icp-brasil",
    "compliance",
}


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def _tokenize(value: str) -> List[str]:
    normalized = _normalize_text(value)
    tokens = re.findall(r"[a-z0-9]{3,}", normalized)
    return [tok for tok in tokens if tok not in _STOPWORDS]


class LegalKnowledgeService:
    """Curated local legal KB retrieval for grounded responses."""

    def __init__(self) -> None:
        self._sources: List[LegalSource] = []
        self._loaded = False

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "LEGAL_KNOWLEDGE_ENABLED", True))

    def _knowledge_path(self) -> Path:
        configured = str(getattr(settings, "LEGAL_KNOWLEDGE_PATH", "app/knowledge/legal/sources.json") or "").strip()
        if configured:
            return Path(configured)
        return Path("app/knowledge/legal/sources.json")

    def _load_sources(self) -> None:
        if self._loaded:
            return

        self._loaded = True
        self._sources = []

        if not self.enabled:
            return

        path = self._knowledge_path()
        if not path.is_absolute():
            # Resolve against current working directory used by the app process.
            path = Path.cwd() / path

        if not path.exists():
            logger.warning("Legal knowledge file not found: %s", path)
            return

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                logger.warning("Invalid legal knowledge format: root must be list")
                return

            for item in raw:
                if not isinstance(item, dict):
                    continue
                source_id = str(item.get("source_id") or "").strip()
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                content = str(item.get("content") or "").strip()
                if not source_id or not title or not content:
                    continue
                self._sources.append(
                    LegalSource(source_id=source_id, title=title, url=url, content=content)
                )
        except Exception:
            logger.warning("Failed to load legal knowledge base", exc_info=True)

    def is_legal_query(self, text: str) -> bool:
        normalized = _normalize_text(text)
        if not normalized:
            return False
        return any(hint in normalized for hint in _LEGAL_HINTS)

    def search(self, query: str, *, limit: Optional[int] = None) -> LegalSearchResult:
        self._load_sources()
        if not self.enabled or not self._sources:
            return LegalSearchResult(query=query, matches=[])

        limit = max(1, int(limit or getattr(settings, "LEGAL_KNOWLEDGE_MAX_SNIPPETS", 3)))
        min_score = max(1, int(getattr(settings, "LEGAL_KNOWLEDGE_MIN_SCORE", 1)))

        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return LegalSearchResult(query=query, matches=[])

        ranked: List[Dict[str, Any]] = []
        for source in self._sources:
            corpus = f"{source.title} {source.content}"
            source_tokens = set(_tokenize(corpus))
            overlap = query_tokens.intersection(source_tokens)
            score = len(overlap)
            if score < min_score:
                continue
            ranked.append(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "content": source.content,
                    "score": score,
                    "overlap": sorted(overlap),
                }
            )

        ranked.sort(key=lambda row: (row["score"], len(row["content"])), reverse=True)
        return LegalSearchResult(query=query, matches=ranked[:limit])

    def build_prompt_block(self, query: str) -> Dict[str, Any]:
        result = self.search(query)
        if not result.matches:
            return {
                "has_evidence": False,
                "prompt_block": "",
                "sources": [],
            }

        lines: List[str] = []
        sources: List[Dict[str, str]] = []
        for idx, match in enumerate(result.matches, 1):
            source_label = f"FONTE {idx}"
            excerpt = str(match.get("content") or "").strip()
            excerpt = excerpt[:900]
            title = str(match.get("title") or "").strip()
            url = str(match.get("url") or "").strip()
            lines.append(f"[{source_label}] {title}")
            if url:
                lines.append(f"URL: {url}")
            lines.append(f"Resumo: {excerpt}")
            lines.append("")
            sources.append({"label": source_label, "title": title, "url": url})

        return {
            "has_evidence": True,
            "prompt_block": "\n".join(lines).strip(),
            "sources": sources,
        }

    def no_evidence_message(self) -> str:
        return (
            "Não localizei base normativa suficiente com segurança na base jurídica interna para responder isso.\n"
            "Próximo passo: valide com jurídico humano e, se quiser, me envie contexto adicional "
            "(tipo de contrato, setor e cláusula) para nova busca."
        )


legal_knowledge_service = LegalKnowledgeService()

