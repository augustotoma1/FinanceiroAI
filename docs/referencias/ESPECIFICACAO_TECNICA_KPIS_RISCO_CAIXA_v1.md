# Especificacao Tecnica - KPIs de Risco de Caixa

Versao: 1.0  
Data: 14/02/2026  
Status: Pronto para implementacao

## 1. Objetivo

Implementar tres KPIs estrategicos no sistema:
1. `indice_risco_caixa` (baixo, medio, alto + score 0-100).
2. `projecao_saldo_15d`.
3. `% concentracao_top3_clientes`.

Esses KPIs devem alimentar:
1. Comando de bot (`/status` e opcionalmente novo `/risco_caixa`).
2. Dashboard API.
3. Alerta diario do CFO.

## 2. Escopo Tecnico

Inclui:
1. Modelagem de metricas e calculo.
2. Servico de agregacao financeira.
3. Persistencia opcional de snapshot diario.
4. Exposicao via API e Telegram.
5. Testes unitarios e de integracao.

Nao inclui:
1. Predicao estatistica/ML de inadimplencia futura.
2. Multiempresa.
3. Dashboard front-end novo (apenas contrato backend).

## 3. Fontes de Dados

## 3.1 Conta Azul

1. Contas a receber (abertas, atrasadas, previstas 15 dias).
2. Contas a pagar (abertas, previstas 15 dias).
3. Saldos em conta financeira.

## 3.2 Banco local

1. Clientes sincronizados.
2. Historico de sincronizacao.
3. Contratos (para analise complementar).

## 4. Definicoes e Formulas

## 4.1 KPI 1 - Projecao de Saldo em 15 Dias

Formula:
`projecao_saldo_15d = saldo_atual_total + receber_15d - pagar_15d`

Campos base:
1. `saldo_atual_total`: soma de contas financeiras ativas.
2. `receber_15d`: soma de nao_pago com vencimento entre hoje e hoje+15.
3. `pagar_15d`: soma de nao_pago com vencimento entre hoje e hoje+15.

## 4.2 KPI 2 - Concentracao Top 3 Clientes

Formula:
`concentracao_top3 = (top3_receber_aberto / total_receber_aberto) * 100`

Regras:
1. Agrupar receber aberto por cliente (`pessoa.nome` ou id da pessoa).
2. Ordenar descrescente e somar 3 maiores.
3. Se `total_receber_aberto == 0`, retornar `0.0`.

## 4.3 KPI 3 - Indice de Risco de Caixa

Subscores (0-100):
1. `risco_saldo_15d`:
   1. `0` se `projecao_saldo_15d >= 0`
   2. `50` se `< 0 e >= -5% faturamento_mensal_referencia`
   3. `100` se `< -5% faturamento_mensal_referencia`
2. `risco_atraso`:
   1. `0` se `atrasado_percentual < 5%`
   2. `50` se `>= 5% e < 8%`
   3. `100` se `>= 8%`
3. `risco_concentracao`:
   1. `0` se `concentracao_top3 <= 40%`
   2. `50` se `> 40% e <= 60%`
   3. `100` se `> 60%`

Score consolidado:
`risco_score = 0.40*risco_saldo_15d + 0.35*risco_atraso + 0.25*risco_concentracao`

Classificacao:
1. `baixo` se `score < 35`
2. `medio` se `score >= 35 e < 65`
3. `alto` se `score >= 65`

## 4.4 Metricas auxiliares

1. `atrasado_percentual = (total_atrasado / faturamento_mensal_referencia) * 100`
2. `faturamento_mensal_referencia`:
   1. Fase 1: parametro em env/config.
   2. Fase 2: calculo automatico por media movel mensal.

## 5. Contrato de Dados (DTO)

```json
{
  "timestamp": "2026-02-14T18:00:00Z",
  "currency": "BRL",
  "saldo_atual_total": 125000.45,
  "receber_15d": 88000.10,
  "pagar_15d": 91300.00,
  "projecao_saldo_15d": 121700.55,
  "total_receber_aberto": 210450.33,
  "top3_receber_aberto": 118020.00,
  "concentracao_top3": 56.08,
  "total_atrasado": 17890.70,
  "atrasado_percentual": 4.47,
  "risco_score": 41.50,
  "risco_nivel": "medio",
  "semaforo": {
    "projecao_15d": "verde",
    "concentracao_top3": "amarelo",
    "atrasado_percentual": "verde",
    "risco_caixa": "amarelo"
  },
  "metas": {
    "atrasado_percentual": "< 5%",
    "tempo_resposta_incidente_horas": "< 4",
    "execucao_rotina_diaria": "100%",
    "concentracao_top3": "<= 40%",
    "projecao_saldo_15d": ">= 0"
  }
}
```

## 6. Alteracoes de Backend

## 6.1 Novo servico

Criar `app/services/cash_risk_service.py` com:
1. `async def compute_cash_risk_snapshot(...) -> dict`
2. `async def get_receber_window(days=15)`
3. `async def get_pagar_window(days=15)`
4. `async def get_current_total_balance()`
5. `def classify_semaphore(value, rule)`
6. `def compute_risk_score(inputs)`

## 6.2 API

Adicionar endpoint protegido:
1. `GET /api/dashboard/cash-risk`

Resposta:
1. DTO completo da secao 5.

## 6.3 Telegram bot

Ajustes recomendados:
1. Incluir resumo de risco no `/status`:
   1. `Risco de Caixa: baixo/medio/alto`
   2. `Projecao 15d: R$ ...`
   3. `Concentracao top3: ...%`
2. Adicionar novo comando opcional `/risco_caixa` com detalhamento completo.
3. Adicionar secao no alerta diario CFO com os 3 KPIs.

## 6.4 Scheduler

Ajustes no scheduler:
1. Job diario de snapshot (ex.: 07:55) antes do alerta CFO.
2. Persistir snapshot para historico e auditoria.

## 7. Persistencia (Opcional, Recomendado)

Criar tabela `cash_risk_snapshots`:
1. `id` (PK)
2. `snapshot_at` (timestamp, index)
3. `saldo_atual_total` (numeric)
4. `receber_15d` (numeric)
5. `pagar_15d` (numeric)
6. `projecao_saldo_15d` (numeric)
7. `total_receber_aberto` (numeric)
8. `top3_receber_aberto` (numeric)
9. `concentracao_top3` (numeric)
10. `total_atrasado` (numeric)
11. `atrasado_percentual` (numeric)
12. `risco_score` (numeric)
13. `risco_nivel` (varchar)
14. `payload_json` (jsonb)

## 8. Configuracoes

Adicionar em `app/config.py`:
1. `FATURAMENTO_MENSAL_REFERENCIA: float = 0`
2. `RISK_WEIGHT_SALDO: float = 0.40`
3. `RISK_WEIGHT_ATRASO: float = 0.35`
4. `RISK_WEIGHT_CONCENTRACAO: float = 0.25`
5. `CASH_RISK_SNAPSHOT_HOUR: int = 7`
6. `CASH_RISK_SNAPSHOT_MINUTE: int = 55`

## 9. Criterios de Aceitacao

1. `/status` retorna risco de caixa e projecao 15d sem erro.
2. Endpoint `/api/dashboard/cash-risk` retorna payload da secao 5.
3. Snapshot diario salvo 1x por dia.
4. Semaforo respeita metas definidas.
5. Testes cobrindo:
   1. cenario verde
   2. cenario amarelo
   3. cenario vermelho
   4. divisao por zero em concentracao
   5. fallback sem dados

## 10. Testes

## 10.1 Unitarios

Criar `tests/test_services/test_cash_risk_service.py` cobrindo:
1. formulas
2. classificacoes
3. arredondamentos
4. regras de semaforo

## 10.2 Integracao

Criar `tests/test_api/test_cash_risk_endpoint.py` cobrindo:
1. autenticacao
2. contrato da resposta
3. codigo HTTP e campos obrigatorios

## 10.3 E2E funcional

1. Rodar `/receber 15d`, `/pagar 15d`, `/saldos`, `/status`.
2. Validar consistencia entre bot e endpoint dashboard.

## 11. Plano de Implantacao

Fase 1 (1 semana):
1. Servico + endpoint + testes unitarios.

Fase 2 (1 semana):
1. Integracao no `/status` e alerta diario.
2. Snapshot diario persistido.

Fase 3 (1 semana):
1. Revisao de thresholds com CFO.
2. Ajuste fino de metas e pesos.

## 12. Riscos Tecnicos e Mitigacao

1. Inconsistencia de nome de cliente no Conta Azul.
Mitigacao: normalizar por id da pessoa quando disponivel.

2. Ausencia de faturamento_mensal_referencia.
Mitigacao: fallback para valor configurado e aviso no payload.

3. APIs externas intermitentes.
Mitigacao: retry controlado, cache curto e status degradado explicito.

4. Divergencia entre horario local e UTC.
Mitigacao: padronizar janela por timezone configuravel.

## 13. Entregaveis

1. Codigo do `cash_risk_service`.
2. Endpoint `/api/dashboard/cash-risk`.
3. Ajuste de `/status` e alerta diario.
4. Migração opcional `cash_risk_snapshots`.
5. Testes unitarios e integracao.
6. Atualizacao do processo operacional e versao executiva.
