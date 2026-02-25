# PR-FLP — Procedimento: Folha de Pagamento
**Versão:** 1.0 | **Data:** 2026-02-24

## 1. Objetivo e Escopo
Processar a folha de pagamento de todos os clientes com precisão, dentro dos prazos legais, garantindo o cálculo correto de salários, encargos (INSS, FGTS, IR) e geração das guias de recolhimento. Aplica-se a todos os clientes ativos com funcionários registrados.

## 2. Responsabilidades (RACI)
| Atividade | Responsável | Aprovador | Consultado | Informado |
|---|---|---|---|---|
| Coleta de documentos do cliente | Analista FLP | Coord. FLP | Cliente | — |
| Processamento no Domínio | Analista FLP | — | — | — |
| Revisão do cálculo | Coord. FLP | — | Analista FLP | — |
| Aprovação final e envio | Coord. FLP | Direção (erros) | — | Cliente |
| Geração e envio de guias | Analista FLP | Coord. FLP | — | Cliente |

## 3. Pré-requisitos
- Dados cadastrais dos funcionários atualizados no Domínio
- Tabelas vigentes de INSS, FGTS e IR carregadas no Domínio (verificar em jan/fev de cada ano)
- Documentos de admissão/demissão/férias do cliente recebidos até D-5 do fechamento
- Acesso ao Autentique para assinatura do holerite/relatório pelo cliente

## 4. Fluxo do Processo
**Entrada:** Documentos do cliente (admissões, demissões, afastamentos, horas extras, adiantamentos)
**Etapas:**
1. **D-5:** Enviar checklist FOR-FLP-01 ao cliente via WhatsApp/e-mail solicitando documentos
2. **D-3:** Cobrar pendências; escalar para Coord. FLP se cliente não responder
3. **D-2:** Lançar dados no Domínio; calcular encargos (INSS empregado/empregador, FGTS, IR)
4. **D-1 (revisão):** Coord. FLP verifica cálculos usando tabela vigente (ver IT-FLP-01 para rescisões)
5. **D-0:** Gerar holerites, DARF/FGTS/GPS/GRF; enviar via Autentique para assinatura do cliente
6. **D+1:** Arquivar documentos assinados; confirmar pagamento das guias com cliente
**Saída:** Holerites assinados, guias geradas, registros arquivados no Domínio

## 5. Pontos de Controle de Qualidade
- [ ] Checklist FOR-FLP-01 respondido pelo cliente antes do processamento
- [ ] Tabela de INSS/FGTS/IR atual (verificar virada de ano)
- [ ] Soma dos proventos − descontos = salário líquido correto (conferir 3 funcionários aleatórios)
- [ ] Guias geradas com código de barras legível e data correta
- [ ] Coord. FLP assina a folha antes do envio ao cliente (dupla checagem)

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo |
|---|---|---|
| Cliente não enviou docs até D-3 | Ligar para cliente; escalar para Coord. FLP | 2h |
| Erro de cálculo descoberto após envio | Reprocessar; emitir errata; registrar em FOR-NC-01 | 24h |
| Guia com código de barras inválido | Regerar no Domínio; não enviar guia inválida | 2h |
| Funcionário não consta no sistema | Verificar admissão; cadastrar antes de processar | 4h |

## 7. KPIs e Metas
| Indicador | Meta | Frequência |
|---|---|---|
| Entregas de folha no prazo (D-0) | 100% | Mensal |
| Reprocessamentos por erro de cálculo | 0 | Mensal |
| Clientes que enviaram docs até D-3 | ≥ 95% | Mensal |
| Guias entregues com antecedência ≥ 2 dias | 100% | Mensal |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção |
|---|---|---|
| Holerites assinados (Autentique) | Domínio + Google Drive / FLP / [Cliente] | 10 anos |
| Guias DARF, GPS, GRF | Domínio + Google Drive / FLP / Guias | 10 anos |
| Checklist FOR-FLP-01 preenchido | Google Drive / FLP / Checklists | 5 anos |
| Registros de não conformidade (FOR-NC-01) | Google Drive / Qualidade | 5 anos |
