# PR-FSC — Procedimento: Fiscal
**Versão:** 1.0 | **Data:** 2026-02-24

## 1. Objetivo e Escopo
Garantir a escrituração fiscal correta, apuração de todos os tributos aplicáveis e entrega de obrigações acessórias dentro dos prazos legais, com zero multas por atraso. Aplica-se a todos os clientes com serviço fiscal contratado (Simples Nacional, Lucro Presumido ou Lucro Real).

## 2. Responsabilidades (RACI)
| Atividade | Responsável | Aprovador | Consultado | Informado |
|---|---|---|---|---|
| Coleta de NFs e documentos (SIEG) | Analista FSC | — | — | — |
| Escrituração fiscal no Domínio | Analista FSC | Coord. FSC | — | — |
| Apuração de tributos | Analista FSC | Coord. FSC | — | — |
| Geração de obrigações acessórias | Coord. FSC | — | Analista FSC | Cliente |
| Validação de prazos e envio | Coord. FSC | Direção (Lucro Real) | — | Cliente |

## 3. Pré-requisitos
- Acesso ao SIEG configurado para captura automática de NFs do cliente
- Regime tributário do cliente confirmado e configurado no Domínio
- Calendário tributário do mês atualizado (DCTF, EFD, SPED, DAS, etc.)
- Certificado digital A1 do cliente válido (verificar vencimento mensalmente)

## 4. Fluxo do Processo
**Entrada:** NFs de entrada/saída capturadas pelo SIEG, documentos de despesas fiscais
**Etapas:**
1. **Dias 1-3:** SIEG captura NFs automaticamente; Analista FSC confere e baixa manualmente as ausentes
2. **Dias 4-8:** Escrituração fiscal no Domínio (entrada e saída por regime tributário)
3. **Dias 9-12:** Apuração de tributos: ICMS, ISS, PIS/COFINS, CSLL, IRPJ (conforme regime)
4. **Dias 13-18:** Gerar obrigações acessórias: DAS (Simples), DCTF, EFD ICMS, EFD Contribuições, SPED
5. **Dias 19-22:** Coord. FSC valida prazos no calendário; validar arquivos antes do envio
6. **Até vencimento legal:** Transmitir obrigações; guardar recibos; notificar cliente
**Saída:** Obrigações transmitidas com recibo, guias de tributos geradas, cliente notificado

## 5. Pontos de Controle de Qualidade
- [ ] 100% das NFs capturadas (comparar quantidade SIEG vs. NFs físicas do cliente)
- [ ] Apuração do DAS/DARF conforme tabela vigente do período (ver IT-FSC-01)
- [ ] Arquivos SPED/EFD validados no PVA antes da transmissão (sem erros críticos)
- [ ] Calendário tributário verificado: nenhum vencimento nas próximas 72h sem ação
- [ ] Recibo de transmissão salvo antes de marcar como concluído

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo |
|---|---|---|
| NF não capturada pelo SIEG | Download manual; investigar causa; reconfigurar SIEG | 24h |
| Erro no PVA ao validar SPED | Corrigir leiaute; revalidar; não transmitir com erro crítico | 48h |
| Prazo de obrigação ≤ 48h sem ação | Prioridade máxima; informar Coord. e Direção imediatamente | 2h |
| Multa recebida por atraso | Registrar em FOR-NC-01; analisar causa; plano de prevenção | 24h |

## 7. KPIs e Metas
| Indicador | Meta | Frequência |
|---|---|---|
| Obrigações fiscais entregues no prazo | 100% | Mensal |
| Multas por atraso em obrigações | R$0 | Mensal |
| NFs não capturadas pelo SIEG | 0 | Mensal |
| Arquivos transmitidos sem retificação | ≥ 98% | Mensal |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção |
|---|---|---|
| Recibos de transmissão (SPED, DCTF, DAS) | Google Drive / FSC / Recibos / [Cliente] / [Ano] | 10 anos |
| Guias de tributos (DAS, DARF, DARE) | Google Drive / FSC / Guias / [Cliente] | 10 anos |
| Arquivos SPED/EFD transmitidos | Domínio + Google Drive / FSC / SPED | 10 anos |
| Calendário tributário mensal | Google Drive / FSC / Calendários | 5 anos |
