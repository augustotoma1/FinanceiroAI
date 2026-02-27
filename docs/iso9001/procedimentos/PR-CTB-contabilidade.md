# PR-CTB — Procedimento: Contabilidade
**Versão:** 2.0 | **Data:** 2026-02-26 | **Revisão:** Inclusão de base legal brasileira

## 1. Objetivo e Escopo
Garantir o registro contábil correto de todas as operações dos clientes, produzindo balancetes e DRE mensais sem divergências, dentro do prazo de fechamento. Aplica-se a todos os clientes com serviço de contabilidade contratado.

### Base Legal
- **Lei 6.404/1976** — Lei das Sociedades por Ações (demonstrações financeiras obrigatórias: Art. 176-188)
- **Lei 11.638/2007** — Convergência às normas internacionais de contabilidade (IFRS)
- **NBC TG (CFC)** — Normas Brasileiras de Contabilidade — Técnicas Gerais (CPC)
- **ITG 2000 (R1) / Resolução CFC 1.330/2011** — Escrituração contábil (livro Diário, Razão, documentação)
- **Código Civil Art. 1.179-1.195** — Obrigação de escrituração para empresários e sociedades empresárias
- **Lei 12.973/2014** — Ajuste entre normas contábeis (IFRS) e legislação tributária
- **NBC TG 23** — Políticas Contábeis, Mudança de Estimativa e Retificação de Erro
- **NBC TG 26 (R5)** — Apresentação das Demonstrações Contábeis

## 2. Responsabilidades (RACI)
| Atividade | Responsável | Aprovador | Consultado | Informado |
|---|---|---|---|---|
| Recepção e classificação de documentos | Analista CTB | — | — | — |
| Lançamentos contábeis no Domínio | Analista CTB | Coord. CTB | — | — |
| Conciliação bancária | Analista CTB | Coord. CTB | Cliente | — |
| Fechamento mensal e DRE | Coord. CTB | Direção | Analista CTB | Cliente |
| Entrega via Onvio | Coord. CTB | — | — | Cliente |
| Escrituração do Livro Diário (ITG 2000) | Analista CTB | Coord. CTB | — | — |
| Revisão de conformidade NBC TG | Coord. CTB | Direção | — | — |

## 3. Pré-requisitos
- Extrato bancário do cliente recebido até dia 5 do mês seguinte
- Notas fiscais de entrada e saída do período disponíveis (via SIEG ou envio direto)
- Plano de contas do cliente configurado no Domínio, aderente às NBC TG e ao plano referencial da RFB
- Acesso ao Onvio para compartilhamento dos balancetes com o cliente
- Livro Diário digital configurado no Domínio conforme ITG 2000 (R1) — Resolução CFC 1.330/2011
- Tabela de depreciação conforme NBC TG 27 (Ativo Imobilizado) atualizada no sistema
- Obrigação de escrituração verificada conforme CC Art. 1.179 (empresários com receita bruta anual > limite MEI)

## 4. Fluxo do Processo
**Entrada:** Extratos bancários, NFs de entrada/saída, comprovantes de despesas
**Etapas:**
1. **Dias 1-5:** Receber e organizar documentos do cliente; solicitar pendências via FOR-CTB-01. Verificar completude conforme CC Art. 1.179 (obrigação de escrituração de todas as operações)
2. **Dias 6-10:** Classificar documentos por conta contábil conforme plano de contas aderente às NBC TG; lançar no Domínio pelo método das partidas dobradas (ITG 2000 R1, item 3) — todo débito corresponde a um crédito de igual valor
3. **Dias 11-15:** Conciliar extrato bancário com lançamentos; resolver divergências. Saldo do extrato deve igualar saldo contábil da conta Bancos (ITG 2000 R1, item 10 — fidedignidade dos registros)
4. **Dias 16-20:** Fechamento do mês; gerar balancete provisório para revisão. Verificar aderência às demonstrações obrigatórias conforme Lei 6.404/1976 Art. 176 (Balanço Patrimonial, DRE, DLPA, DFC, DVA quando aplicável)
5. **Dias 21-25:** Coord. CTB revisa; ajustes finais conforme Lei 11.638/2007 (convergência IFRS); aplicar ajustes tributários conforme Lei 12.973/2014 quando necessário; gerar DRE e balancete definitivos conforme NBC TG 26 (R5) — Apresentação das Demonstrações Contábeis
6. **Até dia 25:** Publicar no Onvio e notificar cliente; registrar no Livro Diário digital conforme ITG 2000 (R1)
**Saída:** Balancete e DRE mensais publicados no Onvio, sem divergências de conciliação, escrituração conforme NBC TG

## 5. Pontos de Controle de Qualidade
- [ ] Todos os documentos do período recebidos antes de iniciar lançamentos (CC Art. 1.179 — completude)
- [ ] Débitos = Créditos em todos os lançamentos — método das partidas dobradas (ITG 2000 R1, item 3; Domínio valida automaticamente)
- [ ] Conciliação bancária: saldo do extrato = saldo contábil (diferença zero) — fidedignidade conforme ITG 2000 R1, item 10
- [ ] Nenhuma conta em aberto no balancete sem justificativa
- [ ] Classificação contábil conforme NBC TG aplicável à natureza da operação
- [ ] Demonstrações financeiras aderentes à Lei 6.404/1976 Art. 176-188 e NBC TG 26 (R5)
- [ ] Ajustes tributários vs. contábeis identificados e registrados conforme Lei 12.973/2014
- [ ] Coord. CTB assina revisão antes da publicação no Onvio

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo | Base Legal |
|---|---|---|---|
| Cliente não enviou documentos até dia 5 | Cobrar via WhatsApp; escalar para Coord. CTB | 24h | CC Art. 1.179 (obrigação de manter escrituração) |
| Divergência na conciliação | Investigar lançamento a lançamento; não fechar sem resolver | 48h | ITG 2000 R1, item 10 (fidedignidade) |
| Classificação contábil incorreta após fechamento | Estorno e reclassificação conforme NBC TG 23 (Retificação de Erro); notificar cliente; FOR-NC-01 | 5 dias | NBC TG 23 — Políticas Contábeis |
| Onvio indisponível | Enviar por e-mail com aviso de sistema; repostar quando normalizar | 2h | — |
| Divergência entre norma contábil e tributária | Registrar ajuste conforme Lei 12.973/2014; documentar no LALUR/LACS | 48h | Lei 12.973/2014 |
| Livro Diário com lançamento fora de ordem cronológica | Corrigir sequência; registrar estorno conforme ITG 2000 (R1) | 24h | ITG 2000 R1, item 5 |

## 7. KPIs e Metas
| Indicador | Meta | Frequência | Base Legal |
|---|---|---|---|
| Fechamento até dia 25 do mês seguinte | 100% dos clientes | Mensal | CC Art. 1.184 (escrituração em ordem cronológica) |
| Divergências de conciliação bancária | 0 no fechamento | Mensal | ITG 2000 R1 (fidedignidade) |
| Reclassificações após fechamento | 0 | Mensal | NBC TG 23 |
| Clientes com acesso ao Onvio atualizado | 100% | Mensal | — |
| Conformidade das demonstrações com NBC TG 26 | 100% | Mensal | NBC TG 26 (R5) / Lei 6.404/1976 |
| Livro Diário completo e sem lacunas | 100% | Mensal | ITG 2000 R1 / Resolução CFC 1.330/2011 |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção | Fundamentação |
|---|---|---|---|
| Balancetes mensais (PDF) | Onvio + Google Drive / CTB / [Cliente] | 10 anos | Lei 6.404/1976 Art. 176 |
| DRE mensal (PDF) | Onvio + Google Drive / CTB / [Cliente] | 10 anos | Lei 6.404/1976 Art. 187 |
| Livro Diário digital | Domínio (SPED Contábil — ECD quando obrigatório) | Permanente | ITG 2000 R1 / CC Art. 1.180 |
| Livro Razão auxiliar | Domínio | 10 anos | ITG 2000 R1, item 8 |
| Comprovantes de lançamentos | Domínio | 10 anos | CC Art. 1.179 |
| Conciliações bancárias | Google Drive / CTB / Conciliações | 10 anos | ITG 2000 R1 |
| Ajustes LALUR/LACS (quando aplicável) | Domínio + Google Drive / CTB | 10 anos | Lei 12.973/2014 |
