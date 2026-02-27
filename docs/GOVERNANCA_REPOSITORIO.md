# Governança de Repositório — SATEC
**Versão:** 1.0  
**Data:** 2026-02-27

## Objetivo
Estabelecer regras mínimas para segurança, rastreabilidade e estabilidade do repositório `agent-financeiro-aisatec`.

## Regras Obrigatórias
1. Não versionar segredos (`.env`, chaves privadas, certificados).
2. Não versionar artefatos de execução (`venv`, `__pycache__`, logs, bancos temporários).
3. Toda mudança em `docs/iso9001` deve manter coerência `PR/IT/FOR`.
4. Toda mudança funcional deve vir com teste (unitário ou integração) quando aplicável.
5. Commits devem ser pequenos, com escopo único e mensagem objetiva.

## Política de Branch e Merge
1. Desenvolvimento em branch dedicada (`codex/*` recomendado).
2. Revisão mínima antes de merge em `main`:
   - impacto funcional
   - impacto em segurança
   - impacto regulatório (quando envolver fiscal/trabalhista/LGPD)
3. Evitar merge de alterações de ambiente local junto com código de produção.

## Checklist Pré-Commit
1. `git status` sem arquivos sensíveis.
2. `.gitignore` cobre novos artefatos locais.
3. Testes relevantes executados.
4. Mudanças documentais ISO com referências válidas.

## Checklist Pós-Merge
1. Confirmar endpoints críticos (`/health`, `/api/dashboard/*`).
2. Confirmar jobs agendados sem erro no startup.
3. Registrar impacto operacional no SGQ quando aplicável.
