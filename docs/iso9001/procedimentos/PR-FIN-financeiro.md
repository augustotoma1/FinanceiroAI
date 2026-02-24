# PR-FIN — Procedimento: Gestão Financeira
**Versão:** 1.0 | **Data:** 2026-02-24 | **Baseado em:** BOT_OPERACAO_FINANCEIRO_v2.md

## 1. Objetivo e Escopo
Garantir o monitoramento diário do fluxo de caixa, cobrança proativa de inadimplentes e geração de relatórios executivos para a Direção. Aplica-se a todos os clientes ativos cujas finanças são gerenciadas pela SATEC via Conta Azul.

## 2. Responsabilidades (RACI)
| Atividade | Responsável | Aprovador | Consultado | Informado |
|---|---|---|---|---|
| Monitoramento diário (bot Telegram) | Agent-Financeiro (AI) | Coord. Financeiro | — | Direção |
| Cobrança de inadimplentes | Coord. Financeiro | Direção | Jurídico | Cliente |
| Conciliação bancária | Analista Financeiro | Coord. Financeiro | — | — |
| Relatório CFO mensal | Coord. Financeiro | Direção | — | Sócios/Direção |

## 3. Pré-requisitos
- Acesso ao Conta Azul configurado para todos os clientes ativos
- Bot Telegram `agent-financeiro-aisatec` operacional (verificar status com `/status`)
- Token de API do Conta Azul válido e registrado em `.env`
- Autentique configurado para assinaturas de documentos financeiros

## 4. Fluxo do Processo
**Entrada:** Dados financeiros dos clientes no Conta Azul
**Etapas:**
1. **Monitoramento diário (automático):** Bot verifica contas a receber, saldo e inadimplência às 8h
2. **Alerta de risco:** Bot envia score de risco de caixa via Telegram; scores ≥ 70 exigem ação imediata
3. **Cobrança (D+1 do vencimento):** Coord. Financeiro contata cliente; registra no Conta Azul
4. **Conciliação bancária (semanal):** Analista cruza extratos com lançamentos no Conta Azul
5. **Fechamento mensal:** Coord. gera relatório `/cfo` via bot e envia à Direção via Autentique
**Saída:** Relatório CFO assinado, inadimplência < 5%, registros atualizados no Conta Azul

## 5. Pontos de Controle de Qualidade
- [ ] Score de risco diário recebido no Telegram (falha = verificar bot com `/status`)
- [ ] Inadimplência < 5% do faturamento total
- [ ] Concentração no top-3 clientes < 40%
- [ ] Conciliação bancária sem divergências antes do fechamento
- [ ] Relatório CFO aprovado pela Direção até dia 5 do mês seguinte

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo |
|---|---|---|
| Bot offline / sem resposta | Reiniciar serviço; acionar suporte técnico | 2h |
| Inadimplência ≥ 5% | Reunião com Direção; plano de cobrança intensivo | 24h |
| Divergência na conciliação > R$100 | Investigar lançamentos; não fechar mês até resolver | 48h |
| Relatório CFO com erro | Recalcular; nova versão antes do envio | 4h |

## 7. KPIs e Metas
| Indicador | Meta | Frequência |
|---|---|---|
| Inadimplência sobre faturamento | < 5% | Mensal |
| Score de risco de caixa | < 70 | Diário |
| Concentração top-3 clientes | < 40% | Mensal |
| Relatório CFO entregue no prazo | 100% (até dia 5) | Mensal |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção |
|---|---|---|
| Relatório CFO mensal (PDF Autentique) | Google Drive / pasta Financeiro | 10 anos |
| Log de cobranças (data, valor, resposta) | Conta Azul + planilha FOR-FIN-01 | 5 anos |
| Alertas de risco (histórico Telegram) | Export mensal em PDF | 2 anos |
| Conciliações bancárias | Google Drive / Financeiro/Conciliações | 10 anos |
