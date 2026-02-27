# PR-FLP — Procedimento: Folha de Pagamento
**Versão:** 2.0 | **Data:** 2026-02-26 | **Revisão:** Inclusão de base legal brasileira

## 1. Objetivo e Escopo
Processar a folha de pagamento de todos os clientes com precisão, dentro dos prazos legais, garantindo o cálculo correto de salários, encargos (INSS, FGTS, IR) e geração das guias de recolhimento. Aplica-se a todos os clientes ativos com funcionários registrados.

### Base Legal
- **CLT (Decreto-Lei nº 5.452/1943):** Art. 457–467 (remuneração e salário), Art. 129–145 (férias anuais), Art. 459 §1º (pagamento até o 5º dia útil do mês subsequente), Art. 477–486 (rescisão contratual)
- **Lei nº 8.212/1991:** Contribuição previdenciária — INSS empregado (alíquotas progressivas) e empregador (20% + RAT)
- **Lei nº 8.036/1990:** FGTS — depósito mensal de 8% sobre remuneração (Art. 15); multa rescisória de 40% (Art. 18)
- **Decreto nº 3.048/1999:** Regulamento da Previdência Social — detalhamento das bases de cálculo e alíquotas
- **eSocial (Decreto nº 8.373/2014):** Obrigações trabalhistas, previdenciárias e fiscais em meio digital — eventos periódicos (S-1200, S-1210, S-1299) e não periódicos (S-2200, S-2299, S-2300)
- **IN RFB nº 2.110/2022:** Normas sobre contribuições previdenciárias — base de incidência, retenções e recolhimento
- **Portaria MTP nº 671/2021:** Registro eletrônico de empregados, jornada de trabalho, CTPS digital e TRCT

## 2. Responsabilidades (RACI)
| Atividade | Responsável | Aprovador | Consultado | Informado |
|---|---|---|---|---|
| Coleta de documentos do cliente | Analista FLP | Coord. FLP | Cliente | — |
| Processamento no Domínio | Analista FLP | — | — | — |
| Revisão do cálculo | Coord. FLP | — | Analista FLP | — |
| Aprovação final e envio | Coord. FLP | Direção (erros) | — | Cliente |
| Geração e envio de guias | Analista FLP | Coord. FLP | — | Cliente |
| Transmissão de eventos eSocial | Analista FLP | Coord. FLP | — | — |

## 3. Pré-requisitos
- Dados cadastrais dos funcionários atualizados no Domínio conforme **Portaria MTP 671/2021** (registro eletrônico)
- Tabelas vigentes de INSS, FGTS e IR carregadas no Domínio, conforme **IN RFB do ano corrente** (verificar publicação em jan/fev de cada ano)
- Alíquotas progressivas do INSS empregado atualizadas conforme **Portaria Interministerial MPS/MF** anual
- Documentos de admissão/demissão/férias do cliente recebidos até D-5 do fechamento
- Acesso ao Autentique para assinatura do holerite/relatório pelo cliente
- Certificado digital A1 do escritório válido para transmissão eSocial

## 4. Fluxo do Processo
**Entrada:** Documentos do cliente (admissões, demissões, afastamentos, horas extras, adiantamentos)
**Etapas:**
1. **D-5:** Enviar checklist FOR-FLP-01 ao cliente via WhatsApp/e-mail solicitando documentos
2. **D-3:** Cobrar pendências; escalar para Coord. FLP se cliente não responder
3. **D-2:** Lançar dados no Domínio; calcular encargos:
   - INSS empregado: alíquotas progressivas conforme **Lei 8.212/1991** e tabela vigente
   - INSS empregador: 20% patronal + RAT (1-3%) conforme **Decreto 3.048/1999**
   - FGTS: 8% sobre remuneração conforme **Lei 8.036/1990 Art. 15**
   - IRRF: tabela progressiva conforme **Decreto 9.580/2018 (RIR)**
4. **D-1 (revisão):** Coord. FLP verifica cálculos usando tabela vigente (ver IT-FLP-01 para rescisões)
5. **D-0:** Gerar holerites, DARF/FGTS/GPS/GRF; enviar via Autentique para assinatura do cliente. Pagamento dos salários deve ocorrer até o **5º dia útil do mês subsequente (CLT Art. 459 §1º)**
6. **D+1:** Arquivar documentos assinados; confirmar pagamento das guias com cliente
7. **Até dia 15 do mês seguinte:** Transmitir evento **S-1299 (fechamento)** no eSocial conforme prazos do **Decreto 8.373/2014**
**Saída:** Holerites assinados, guias geradas, eventos eSocial transmitidos, registros arquivados no Domínio

## 5. Pontos de Controle de Qualidade
- [ ] Checklist FOR-FLP-01 respondido pelo cliente antes do processamento
- [ ] Tabela de INSS/FGTS/IR atual conforme **IN RFB vigente** (verificar virada de ano)
- [ ] Soma dos proventos − descontos = salário líquido correto (conferir 3 funcionários aleatórios)
- [ ] Guias geradas com código de barras legível e data correta
- [ ] Coord. FLP assina a folha antes do envio ao cliente (dupla checagem)
- [ ] Eventos eSocial (S-1200 remuneração, S-1210 pagamento) transmitidos dentro do prazo legal — **até o dia 15 do mês seguinte (Decreto 8.373/2014)**
- [ ] Eventos não periódicos (S-2200 admissão, S-2299 desligamento) transmitidos conforme prazos específicos do eSocial

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo |
|---|---|---|
| Cliente não enviou docs até D-3 | Ligar para cliente; escalar para Coord. FLP | 2h |
| Erro de cálculo descoberto após envio | Reprocessar; emitir errata; registrar em FOR-NC-01 | 24h |
| Guia com código de barras inválido | Regerar no Domínio; não enviar guia inválida | 2h |
| Funcionário não consta no sistema | Verificar admissão; cadastrar antes de processar; transmitir S-2200 no eSocial | 4h |
| Evento eSocial rejeitado | Analisar erro no retorno; corrigir e retransmitir antes do prazo legal | 24h |
| Descumprimento do prazo do **Art. 459 §1º CLT** | Notificar cliente imediatamente; registrar em FOR-NC-01; orientar sobre riscos trabalhistas | imediato |

## 7. KPIs e Metas
| Indicador | Meta | Frequência | Base Legal |
|---|---|---|---|
| Entregas de folha no prazo (D-0) | 100% | Mensal | CLT Art. 459 §1º |
| Reprocessamentos por erro de cálculo | 0 | Mensal | — |
| Clientes que enviaram docs até D-3 | ≥ 95% | Mensal | — |
| Guias entregues com antecedência ≥ 2 dias | 100% | Mensal | — |
| Eventos eSocial transmitidos no prazo | 100% | Mensal | Decreto 8.373/2014 |
| Compliance com prazos legais CLT/INSS/FGTS | 100% | Mensal | CLT, Lei 8.212, Lei 8.036 |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção | Fundamentação |
|---|---|---|---|
| Holerites assinados (Autentique) | Domínio + Google Drive / FLP / [Cliente] | 10 anos | CLT Art. 464 |
| Guias DARF, GPS, GRF | Domínio + Google Drive / FLP / Guias | 10 anos | Lei 8.212/1991 |
| Recibos de transmissão eSocial | Google Drive / FLP / eSocial | 10 anos | Decreto 8.373/2014 |
| Checklist FOR-FLP-01 preenchido | Google Drive / FLP / Checklists | 5 anos | Controle interno |
| Registros de não conformidade (FOR-NC-01) | Google Drive / Qualidade | 5 anos | ISO 9001 cláusula 10.2 |
