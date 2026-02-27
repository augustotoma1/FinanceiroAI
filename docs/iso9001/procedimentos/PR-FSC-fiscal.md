# PR-FSC — Procedimento: Fiscal
**Versão:** 2.0 | **Data:** 2026-02-26 | **Revisão:** Inclusão de base legal tributária brasileira

## 1. Objetivo e Escopo
Garantir a escrituração fiscal correta, apuração de todos os tributos aplicáveis e entrega de obrigações acessórias dentro dos prazos legais, com zero multas por atraso. Aplica-se a todos os clientes com serviço fiscal contratado (Simples Nacional, Lucro Presumido ou Lucro Real).

### Base Legal
- **CTN — Código Tributário Nacional (Lei 5.172/1966)** — Normas gerais de direito tributário: obrigação tributária (Art. 113-138), lançamento (Art. 142-150), crédito tributário (Art. 139-141), prescrição e decadência (Art. 150 §4º, Art. 173-174), multa moratória (Art. 161)
- **LC 87/1996 (Lei Kandir)** — ICMS: fato gerador, base de cálculo, alíquotas interestaduais, crédito fiscal, substituição tributária
- **LC 116/2003** — ISS: lista de serviços tributáveis, local de incidência, alíquota mínima 2% (LC 157/2016) e máxima 5%
- **LC 123/2006** — Simples Nacional: enquadramento, limites de receita bruta (Art. 3º), alíquotas por anexo (Art. 18), exclusão (Art. 29-34)
- **Resolução CGSN 140/2018** — Regulamento do Simples Nacional: cálculo do DAS (Art. 16-26), obrigações acessórias (Art. 63-72), DEFIS (Art. 66)
- **Decreto 9.580/2018 (RIR)** — Regulamento do Imposto de Renda: Lucro Presumido (Art. 587-601), Lucro Real (Art. 257-586), retenções na fonte
- **IN RFB 2.043/2021** — EFD Contribuições: escrituração digital de PIS/PASEP e COFINS
- **Ajuste SINIEF 07/2005** — NF-e: obrigatoriedade, leiaute, validação, cancelamento, carta de correção
- **Convênio ICMS 143/2006** — SPED Fiscal (EFD ICMS/IPI): escrituração digital de ICMS e IPI
- **MP 2.200-2/2001** — ICP-Brasil: validade jurídica de documentos eletrônicos com certificado digital
- **Lei 9.430/1996** — DCTF: declaração de débitos e créditos tributários federais
- **IN RFB 2.005/2021** — ECF (Escrituração Contábil Fiscal): obrigatória para Lucro Real e Presumido

## 2. Responsabilidades (RACI)
| Atividade | Responsável | Aprovador | Consultado | Informado |
|---|---|---|---|---|
| Coleta de NFs e documentos (SIEG) | Analista FSC | — | — | — |
| Escrituração fiscal no Domínio | Analista FSC | Coord. FSC | — | — |
| Apuração de tributos por regime | Analista FSC | Coord. FSC | — | — |
| Geração de obrigações acessórias (SPED, EFD, DCTF, DEFIS) | Coord. FSC | — | Analista FSC | Cliente |
| Validação de prazos e transmissão | Coord. FSC | Direção (Lucro Real) | — | Cliente |
| Controle de certificados digitais (ICP-Brasil) | Analista FSC | Coord. FSC | — | Cliente |
| Acompanhamento de alterações legislativas | Coord. FSC | Direção | — | Equipe FSC |

## 3. Pré-requisitos
- Acesso ao SIEG configurado para captura automática de NFs do cliente
- Regime tributário do cliente confirmado e configurado no Domínio:
  - **Simples Nacional:** conforme LC 123/2006 Art. 3º (limite RB12 ≤ R$4,8 milhões)
  - **Lucro Presumido:** conforme Decreto 9.580/2018 Art. 587-601 (limite receita bruta ≤ R$78 milhões/ano)
  - **Lucro Real:** obrigatório para empresas acima dos limites ou com atividades específicas (Decreto 9.580/2018 Art. 257)
- Calendário tributário do mês atualizado (FOR-FSC-01) com todos os vencimentos legais
- **Certificado digital A1 do cliente válido**, emitido por Autoridade Certificadora credenciada pela ICP-Brasil conforme MP 2.200-2/2001 — verificar vencimento mensalmente e alertar cliente com 60 dias de antecedência
- Tabelas de alíquotas atualizadas:
  - Simples Nacional: Anexos I-V conforme LC 123/2006 Art. 18 e Resolução CGSN 140/2018
  - ICMS: alíquotas internas e interestaduais conforme LC 87/1996 e regulamento estadual (RICMS-MT)
  - ISS: alíquota do município conforme LC 116/2003 e legislação municipal
  - PIS/COFINS: regime cumulativo (Lei 9.718/1998) ou não cumulativo (Leis 10.637/2002 e 10.833/2003)
- Acesso ao PGDAS-D (Simples Nacional), e-CAC (RFB), SEFAZ estadual e portal da Prefeitura

## 4. Fluxo do Processo
**Entrada:** NFs de entrada/saída capturadas pelo SIEG, documentos de despesas fiscais
**Etapas:**
1. **Dias 1-3:** SIEG captura NFs automaticamente conforme Ajuste SINIEF 07/2005 (NF-e); Analista FSC confere e baixa manualmente as NFs não capturadas. Validar XML das NFs conforme leiaute vigente da NF-e (Ajuste SINIEF 07/2005, cláusula nona)
2. **Dias 4-8:** Escrituração fiscal no Domínio por regime tributário:
   - **Simples Nacional:** classificação conforme Anexos I-V (LC 123/2006 Art. 18); segregação de receitas por atividade (Resolução CGSN 140/2018 Art. 25)
   - **Lucro Presumido:** escrituração de receitas conforme Decreto 9.580/2018 Art. 587; base presumida por atividade (8%, 16% ou 32%)
   - **Lucro Real:** escrituração completa conforme Decreto 9.580/2018 Art. 257; adições e exclusões no LALUR
   - **ICMS:** escrituração de entradas e saídas conforme LC 87/1996; créditos fiscais (Art. 20); substituição tributária quando aplicável
   - **ISS:** escrituração conforme LC 116/2003; verificar local de incidência (Art. 3º) e retenções
3. **Dias 9-12:** Apuração de tributos:
   - **DAS** (Simples): cálculo da alíquota efetiva conforme Resolução CGSN 140/2018 Art. 21 (ver IT-FSC-01)
   - **ICMS** (LP/LR): débito − crédito conforme LC 87/1996 Art. 24; DIFAL quando aplicável
   - **ISS** (LP/LR): conforme alíquota municipal e LC 116/2003
   - **PIS/COFINS** (LP cumulativo): Lei 9.718/1998 — 0,65% PIS + 3% COFINS sobre faturamento
   - **PIS/COFINS** (LR não cumulativo): Leis 10.637/2002 e 10.833/2003 — 1,65% PIS + 7,6% COFINS com créditos
   - **IRPJ/CSLL** (LP): base presumida × 15% IRPJ (+10% adicional se base > R$60mil/trimestre) + 9% CSLL
   - **IRPJ/CSLL** (LR): lucro líquido ajustado × 15% IRPJ (+10% adicional) + 9% CSLL
4. **Dias 13-18:** Gerar obrigações acessórias conforme legislação:
   - **DAS** — PGDAS-D mensal (Resolução CGSN 140/2018 Art. 38) — vencimento dia 20
   - **DCTF** — Declaração mensal conforme Lei 9.430/1996 e IN RFB vigente — vencimento dia 15
   - **EFD ICMS/IPI** — Convênio ICMS 143/2006 — transmissão mensal via PVA
   - **EFD Contribuições** — IN RFB 2.043/2021 — PIS/COFINS digital — vencimento dia 10
   - **DEFIS** — Declaração anual do Simples (Resolução CGSN 140/2018 Art. 66) — vencimento 31/março
   - **ECF** — Escrituração Contábil Fiscal anual (IN RFB 2.005/2021) — LP e LR — vencimento julho
   - **SPED Fiscal** — Escrituração digital de ICMS/IPI conforme Convênio ICMS 143/2006
5. **Dias 19-22:** Coord. FSC valida prazos no calendário FOR-FSC-01; validar arquivos SPED/EFD no PVA (Programa Validador e Assinador) antes da transmissão — assinatura com certificado digital A1 conforme MP 2.200-2/2001
6. **Até vencimento legal:** Transmitir obrigações com certificado digital; guardar recibos de transmissão; notificar cliente com guias e prazos de pagamento. Atenção aos prazos legais — atraso gera multa moratória conforme CTN Art. 161 (juros SELIC) e multa específica por obrigação acessória conforme Art. 57 da MP 2.158-35/2001
**Saída:** Obrigações transmitidas com recibo, guias de tributos geradas e enviadas ao cliente, escrituração digital completa

## 5. Pontos de Controle de Qualidade
- [ ] 100% das NFs capturadas — comparar quantidade SIEG vs. NFs no portal da SEFAZ (consulta por CNPJ). XML validado conforme leiaute Ajuste SINIEF 07/2005
- [ ] Regime tributário do cliente conferido e correto no Domínio — LC 123/2006 (Simples), Decreto 9.580/2018 (LP/LR)
- [ ] Apuração do DAS/DARF conforme tabela vigente do período (ver IT-FSC-01 para Simples; alíquotas por regime para LP/LR)
- [ ] Créditos de ICMS corretamente apropriados conforme LC 87/1996 Art. 20 (vedações Art. 20 §1º verificadas)
- [ ] Créditos de PIS/COFINS verificados conforme Leis 10.637/2002 e 10.833/2003 (regime não cumulativo)
- [ ] Arquivos SPED/EFD validados no PVA antes da transmissão — zero erros críticos e zero avisos impeditivos
- [ ] Certificado digital A1 do cliente válido e dentro da validade (MP 2.200-2/2001) — verificação mensal
- [ ] Calendário tributário FOR-FSC-01 verificado: nenhum vencimento nas próximas 72h sem ação
- [ ] Recibo de transmissão salvo e arquivado antes de marcar obrigação como concluída

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo | Base Legal |
|---|---|---|---|
| NF não capturada pelo SIEG | Download manual do XML na SEFAZ; investigar causa; reconfigurar SIEG | 24h | Ajuste SINIEF 07/2005 |
| Erro no PVA ao validar SPED/EFD | Corrigir leiaute no Domínio; revalidar; não transmitir com erro crítico | 48h | Convênio ICMS 143/2006 / IN RFB 2.043/2021 |
| Prazo de obrigação ≤ 48h sem ação | Prioridade máxima; informar Coord. FSC e Direção imediatamente | 2h | CTN Art. 161 (multa moratória — juros SELIC) |
| Multa recebida por atraso | Registrar em FOR-NC-01; analisar causa raiz; plano de prevenção; verificar possibilidade de denúncia espontânea (CTN Art. 138) para exclusão de multa punitiva | 24h | CTN Art. 138 (denúncia espontânea), Art. 161 |
| Certificado digital A1 vencido | Notificar cliente imediatamente; não transmitir sem certificado válido; auxiliar na renovação | 4h | MP 2.200-2/2001 |
| Divergência entre apuração e guia de pagamento | Recalcular; verificar se houve retificação; corrigir antes do vencimento | 24h | CTN Art. 150 §4º (decadência 5 anos) |
| Cliente ultrapassou limite do Simples Nacional | Alertar Coord. FSC e Direção; iniciar planejamento de exclusão conforme LC 123/2006 Art. 29-34; definir novo regime tributário | 48h | LC 123/2006 Art. 3º §1º e Art. 29-34 |
| NF-e cancelada ou com carta de correção após escrituração | Ajustar escrituração conforme Ajuste SINIEF 07/2005 cláusula décima segunda (cancelamento) ou décima quarta-A (CC-e) | 24h | Ajuste SINIEF 07/2005 |

## 7. KPIs e Metas
| Indicador | Meta | Frequência | Base Legal |
|---|---|---|---|
| Obrigações fiscais entregues no prazo legal | 100% | Mensal | CTN Art. 113 §2º (obrigação acessória) |
| Multas por atraso em obrigações | R$0 | Mensal | CTN Art. 161 |
| NFs não capturadas pelo SIEG | 0 | Mensal | Ajuste SINIEF 07/2005 |
| Arquivos transmitidos sem retificação posterior | ≥ 98% | Mensal | IN RFB 2.043/2021 / Convênio ICMS 143/2006 |
| Certificados digitais vencidos sem renovação | 0 | Mensal | MP 2.200-2/2001 |
| Clientes com regime tributário revisado anualmente | 100% | Anual | LC 123/2006 Art. 3º / Decreto 9.580/2018 |
| Denúncias espontâneas realizadas quando aplicável | 100% dos casos elegíveis | Por ocorrência | CTN Art. 138 |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção | Fundamentação |
|---|---|---|---|
| Recibos de transmissão (SPED, DCTF, DAS, EFD, DEFIS, ECF) | Google Drive / FSC / Recibos / [Cliente] / [Ano] | 10 anos | CTN Art. 173-174 (decadência e prescrição) |
| Guias de tributos (DAS, DARF, DARE, ISS) | Google Drive / FSC / Guias / [Cliente] | 10 anos | CTN Art. 150 §4º |
| Arquivos SPED/EFD transmitidos (XML + recibo) | Domínio + Google Drive / FSC / SPED | 10 anos | Convênio ICMS 143/2006 / IN RFB 2.043/2021 |
| Calendário tributário mensal (FOR-FSC-01) | Google Drive / FSC / Calendários | 5 anos | — |
| XMLs de NF-e recebidas | Domínio + Google Drive / FSC / NFs / [Cliente] | 5 anos | Ajuste SINIEF 07/2005 cláusula nona |
| Cópia do certificado digital A1 (metadados — não a chave privada) | Google Drive / FSC / Certificados / [Cliente] | Até vencimento + 1 ano | MP 2.200-2/2001 |
| Memória de cálculo de apurações (LP e LR) | Domínio + Google Drive / FSC / Apurações | 10 anos | Decreto 9.580/2018 |
| LALUR/LACS (Lucro Real) | Domínio (integrado à ECF) | 10 anos | Decreto 9.580/2018 Art. 302 |
