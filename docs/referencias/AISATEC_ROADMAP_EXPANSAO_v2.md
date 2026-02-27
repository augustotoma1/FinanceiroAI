# AISATEC ROADMAP DE EXPANSAO v2

Versao: 2.0  
Data: 14/02/2026  
Status: Aprovado para execucao por Stage-Gate

## 1. Diretriz Executiva

Transformar o AISATEC de bot operacional em funcionario virtual financeiro com autonomia controlada, governanca formal e risco monitorado.

## 2. Mudancas Estruturais Aprovadas

## 2.1 Stage-Gate obrigatorio por fase

Nenhuma fase avanca sem aprovacao formal do comite (Coordenacao Financeira + CFO + Tecnico).

Criterios obrigatorios por gate:
1. Qualidade minima (KPIs da fase atingidos).
2. Avaliacao de risco tecnico e operacional.
3. Aprovacao orcamentaria da fase seguinte.
4. Validacao do sponsor executivo (CFO).

Exemplo oficial de gate Fase 1 -> Fase 2:
1. Taxa de entrega de email >= 95%.
2. 30 dias sem incidente critico.
3. Baseline oficial validado.
4. Compliance juridico aprovado.

## 2.2 Modelo financeiro oficial (CAPEX + OPEX)

A previsao passa a considerar:

1. CAPEX (implementacao)
- Desenvolvimento IA.
- Integracoes (WhatsApp, voz, CRM, dashboard).
- QA e seguranca.
- Setup de Voice AI.

2. OPEX (operacao recorrente)
- Infraestrutura.
- APIs (LLM, voz, WhatsApp).
- Observabilidade.
- Operacao humana/BPO.

Modelo de apresentacao financeira:
1. Cenario conservador.
2. Cenario base.
3. Cenario expansao.
4. ROI projetado em 6 e 12 meses.

## 2.3 Compliance formal para cobranca automatizada

A Fase 2 fica condicionada a politica juridica formal aprovada.

Estrutura minima obrigatoria:
1. Base legal: execucao de contrato + legitimo interesse (LGPD Art. 7o).
2. Consentimento registrado no onboarding.
3. Opt-out automatico e auditavel.
4. Frequencia maxima: 1 contato/dia.
5. Janela de contato: 08h-18h ligacoes e ate 20h mensagens.
6. Retencao de gravacoes: 12 meses.
7. Anonimizacao apos prazo legal.
8. Log integral de interacoes.

## 2.4 Matriz oficial de alcada e autonomia

| Regra | Limite oficial |
|---|---|
| Prazo adicional automatico | Ate 5 dias uteis |
| Desconto automatico | Ate 10% ou R$ 3.000 (o menor) |
| Parcelamento | Maximo 3 parcelas sem juros |
| Valores acima de R$ 20.000 | Aprovacao CFO |
| Negociacao fora da matriz | Escalonamento obrigatorio |

Observacao: limites devem ser implementados como guardrails tecnicos do agente.

## 2.5 Baseline oficial e formulas de KPI

Baseline oficial:
1. Preferencial: ultimos 12 meses.
2. Excecao: 6 meses se historico menor.
3. Fonte unica: Conta Azul + PostgreSQL consolidado.

Formulas oficiais:

1. Inadimplencia (%)
`(valor_vencido_mais_30_dias / faturamento_ultimos_30_dias) * 100`

2. Taxa de recuperacao
`valor_recuperado / valor_cobrado_no_periodo`

3. PMR
`receita_a_receber / receita_media_diaria`

Governanca da metrica:
1. Responsavel: Coordenacao Financeira.
2. Periodicidade: mensal.

## 2.6 Cronograma condicionado a capacidade

Premissas minimas aprovadas:
1. Time minimo: 1 Tech Lead + 1 Dev + 1 Analista Financeiro.
2. Dedicacao minima: 60% nas Fases 1-3.
3. Homologacoes externas: 5-10 dias por integracao.
4. Buffer tecnico: 15%.

Regra:
Se premissas nao atendidas, replanejamento obrigatorio antes de avancar.

## 2.7 Padrao institucional de qualidade documental

1. Revisao ortografica completa antes de circulacao externa.
2. Padronizacao de termos e status.
3. Versao final com aprovacao formal registrada.

## 3. Respostas Oficiais Registradas (Governanca)

1. X dias de negociacao autonoma: 5 dias uteis.
2. Y alcada financeira autonoma: ate 10% ou R$ 3.000 (o menor).
3. Baseline oficial: 12 meses (preferencial), 6 meses (historico menor).
4. Politica juridica formal: obrigatoria antes da Fase 2.

## 4. Gate Matrix (Resumo Executivo)

| Gate | Condicao de entrada | Condicao de saida | Aprovadores |
|---|---|---|---|
| G1 (inicio F1) | Budget CAPEX F1 aprovado | KPIs F1 + risco controlado | Coordenacao Tecnica + Financeiro |
| G2 (inicio F2) | F1 encerrada sem pendencia critica | Compliance juridico aprovado + baseline validado | CFO + Juridico + TI |
| G3 (inicio F3) | Canais operacionais estaveis | KPI cobranca e qualidade de contato aprovados | CFO + Operacoes |
| G4 (inicio F4) | Agente autonomo com guardrails validados | ROI parcial positivo e readiness de escala | CFO + Diretoria |

## 5. Backlog de Implantacao Imediata (30 dias)

1. Publicar politica de contato automatizado (juridico).
2. Implementar guardrails da matriz de alcada no agente.
3. Publicar baseline oficial e formulas em dashboard.
4. Habilitar semaforo executivo com metas aprovadas.
5. Instituir ritual quinzenal de stage-gate.

## 6. Anexos Recomendados

1. Politica de Contato Automatizado (documento juridico).
2. Matriz de Alcada Operacional (versao assinada).
3. Baseline de KPIs (12 meses).
4. Modelo financeiro CAPEX/OPEX com ROI 6/12 meses.
