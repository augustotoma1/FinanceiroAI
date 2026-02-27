# PR-FIN — Procedimento: Gestão Financeira
**Versão:** 2.0 | **Data:** 2026-02-26 | **Baseado em:** BOT_OPERACAO_FINANCEIRO_v2.md

## 1. Objetivo e Escopo
Garantir o monitoramento diário do fluxo de caixa, cobrança proativa de inadimplentes e geração de relatórios executivos para a Direção. Aplica-se a todos os clientes ativos cujas finanças são gerenciadas pela SATEC via Conta Azul.

### Base Legal
- **CDC (Lei 8.078/1990)** — Relações de consumo aplicáveis à prestação de serviços contábeis; Art. 42 (cobrança de débitos sem exposição do consumidor); Art. 46 (transparência nas obrigações)
- **CTN (Lei 5.172/1966)** — Normas gerais de direito tributário; Art. 113 (obrigação tributária principal e acessória); Art. 156 (extinção do crédito tributário pelo pagamento)
- **Lei 6.404/1976** — Lei das S/A; Art. 176-188 (demonstrações financeiras obrigatórias: balanço patrimonial, DRE, fluxo de caixa)
- **CC (Lei 10.406/2002) Art. 389-420** — Inadimplemento das obrigações; Art. 394 (mora); Art. 395 (perdas e danos por atraso); Art. 397 (constituição em mora)
- **Lei 8.137/1990** — Crimes contra a ordem tributária; Art. 1º-2º (supressão ou redução de tributo); Art. 11 (omissão de informações)
- **Resolução CFC 1.374/2011 (NBC TG Estrutura Conceitual)** — Elaboração e divulgação de relatório contábil-financeiro (DRE, fluxo de caixa, balanço)
- **NBC TG 03 (R3) — Demonstração dos Fluxos de Caixa** — Classificação dos fluxos em operacional, investimento e financiamento
- **Lei 12.682/2012** — Elaboração e arquivamento de documentos em meios eletromagnéticos (valida arquivamento digital de relatórios)

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
- Plano de contas financeiro alinhado à NBC TG Estrutura Conceitual (Resolução CFC 1.374/2011)
- Modelo de DRE e fluxo de caixa conforme Lei 6.404/1976 Art. 176 e NBC TG 03 (R3)

## 4. Fluxo do Processo
**Entrada:** Dados financeiros dos clientes no Conta Azul
**Etapas:**
1. **Monitoramento diário (automático):** Bot verifica contas a receber, saldo e inadimplência às 8h — relatório estruturado conforme NBC TG 03 (R3) (classificação operacional/investimento/financiamento)
2. **Alerta de risco:** Bot envia score de risco de caixa via Telegram; scores ≥ 70 exigem ação imediata — parâmetros de risco baseados em indicadores de liquidez conforme NBC TG Estrutura Conceitual
3. **Cobrança (D+1 do vencimento):** Coord. Financeiro contata cliente; registra no Conta Azul — cobrança conforme CDC Art. 42 (sem exposição ao ridículo ou constrangimento); constituição em mora conforme CC Art. 397
4. **Conciliação bancária (semanal):** Analista cruza extratos com lançamentos no Conta Azul — conciliação deve refletir fielmente a posição patrimonial conforme NBC TG Estrutura Conceitual (representação fidedigna)
5. **Fechamento mensal:** Coord. gera relatório `/cfo` via bot e envia à Direção via Autentique — DRE e fluxo de caixa conforme Lei 6.404/1976 Art. 176-188; assinatura digital válida conforme Lei 12.682/2012
**Saída:** Relatório CFO assinado, inadimplência < 5%, registros atualizados no Conta Azul

## 5. Pontos de Controle de Qualidade
- [ ] Score de risco diário recebido no Telegram (falha = verificar bot com `/status`)
- [ ] Inadimplência < 5% do faturamento total — monitorar conforme CC Art. 394-397 (mora e inadimplemento)
- [ ] Concentração no top-3 clientes < 40% — mitigação de risco conforme princípio da prudência (NBC TG Estrutura Conceitual)
- [ ] Conciliação bancária sem divergências antes do fechamento — representação fidedigna conforme Resolução CFC 1.374/2011
- [ ] Relatório CFO aprovado pela Direção até dia 5 do mês seguinte — prazo interno alinhado às demonstrações obrigatórias (Lei 6.404/1976 Art. 176)
- [ ] Procedimentos de cobrança em conformidade com CDC Art. 42 (cobrança ética e sem constrangimento)

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo | Base Legal |
|---|---|---|---|
| Bot offline / sem resposta | Reiniciar serviço; acionar suporte técnico | 2h | — (operacional) |
| Inadimplência ≥ 5% | Reunião com Direção; plano de cobrança intensivo conforme CC Art. 397 e CDC Art. 42 | 24h | CC Art. 394-397; CDC Art. 42 |
| Divergência na conciliação > R$100 | Investigar lançamentos; não fechar mês até resolver — representação fidedigna obrigatória | 48h | NBC TG Estrutura Conceitual; Resolução CFC 1.374/2011 |
| Relatório CFO com erro | Recalcular conforme NBC TG 03 (R3); nova versão antes do envio | 4h | Lei 6.404/1976 Art. 176; NBC TG 03 (R3) |
| Suspeita de irregularidade tributária | Notificar Direção imediatamente; documentar para proteção legal | imediato | Lei 8.137/1990 Art. 1º-2º |

## 7. KPIs e Metas
| Indicador | Meta | Frequência | Base Legal |
|---|---|---|---|
| Inadimplência sobre faturamento | < 5% | Mensal | CC Art. 389-420 (inadimplemento) |
| Score de risco de caixa | < 70 | Diário | NBC TG Estrutura Conceitual (prudência) |
| Concentração top-3 clientes | < 40% | Mensal | NBC TG Estrutura Conceitual (risco) |
| Relatório CFO entregue no prazo | 100% (até dia 5) | Mensal | Lei 6.404/1976 Art. 176 |
| Cobranças realizadas conforme CDC | 100% | Mensal | CDC Art. 42 |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção | Fundamentação |
|---|---|---|---|
| Relatório CFO mensal (PDF Autentique) | Google Drive / pasta Financeiro | 10 anos | Lei 6.404/1976 Art. 176; Lei 12.682/2012 (arquivo eletrônico) |
| Log de cobranças (data, valor, resposta) | Conta Azul + planilha FOR-FIN-01 | 5 anos | CDC Art. 42; CC Art. 397 (comprovação de mora) |
| Alertas de risco (histórico Telegram) | Export mensal em PDF | 2 anos | NBC TG Estrutura Conceitual (documentação de riscos) |
| Conciliações bancárias | Google Drive / Financeiro/Conciliações | 10 anos | Resolução CFC 1.374/2011; NBC TG 03 (R3) |
| DRE e Fluxo de Caixa mensais | Onvio + Google Drive / Financeiro | 10 anos | Lei 6.404/1976 Art. 176-188; NBC TG 26 (R5) |
