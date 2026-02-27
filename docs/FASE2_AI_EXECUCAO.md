# Fase 2 AI — Guia de Execução
**Data:** 2026-02-27

## Objetivo
Operacionalizar a expansão AI em 3 níveis com validação contínua por API e evidência no SGQ.

## Níveis
1. Validação (pré-entrega): consistência de dados e riscos.
2. Comunicação: cobrança/notificação automatizada com rastreabilidade.
3. Apoio à decisão: recomendações com guardrails e aprovação humana.

## Endpoint de Prontidão
`GET /api/dashboard/ai-employee/phase2-readiness`

O endpoint retorna:
- status dos níveis 1, 2 e 3 (`ready`, `partial`, `blocked`)
- checks objetivos por nível
- probes de integração (sync, risco, contratos, canais)
- próximos passos recomendados

## Critério de Go-Live por Nível
### Nível 1
- `level_1_validation.status = ready`

### Nível 2
- `level_2_communication.status = ready`
- canal Telegram ativo + ao menos um canal de cobrança habilitado

### Nível 3
- `level_3_decision_support.status = ready`
- AI Employee habilitado, logging ativo e operação fora de dry-run

## Rotina Recomendada
1. Consultar endpoint de prontidão diariamente.
2. Registrar resultado em reunião operacional.
3. Tratar pendências apontadas em `next_steps`.
4. Atualizar NC no SGQ quando houver desvio recorrente.
