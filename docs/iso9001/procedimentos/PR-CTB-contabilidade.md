# PR-CTB — Procedimento: Contabilidade
**Versão:** 1.0 | **Data:** 2026-02-24

## 1. Objetivo e Escopo
Garantir o registro contábil correto de todas as operações dos clientes, produzindo balancetes e DRE mensais sem divergências, dentro do prazo de fechamento. Aplica-se a todos os clientes com serviço de contabilidade contratado.

## 2. Responsabilidades (RACI)
| Atividade | Responsável | Aprovador | Consultado | Informado |
|---|---|---|---|---|
| Recepção e classificação de documentos | Analista CTB | — | — | — |
| Lançamentos contábeis no Domínio | Analista CTB | Coord. CTB | — | — |
| Conciliação bancária | Analista CTB | Coord. CTB | Cliente | — |
| Fechamento mensal e DRE | Coord. CTB | Direção | Analista CTB | Cliente |
| Entrega via Onvio | Coord. CTB | — | — | Cliente |

## 3. Pré-requisitos
- Extrato bancário do cliente recebido até dia 5 do mês seguinte
- Notas fiscais de entrada e saída do período disponíveis (via SIEG ou envio direto)
- Plano de contas do cliente configurado no Domínio
- Acesso ao Onvio para compartilhamento dos balancetes com o cliente

## 4. Fluxo do Processo
**Entrada:** Extratos bancários, NFs de entrada/saída, comprovantes de despesas
**Etapas:**
1. **Dias 1-5:** Receber e organizar documentos do cliente; solicitar pendências via FOR-CTB-01
2. **Dias 6-10:** Classificar documentos por conta contábil; lançar no Domínio
3. **Dias 11-15:** Conciliar extrato bancário com lançamentos; resolver divergências
4. **Dias 16-20:** Fechamento do mês; gerar balancete provisório para revisão
5. **Dias 21-25:** Coord. CTB revisa; ajustes finais; gerar DRE e balancete definitivos
6. **Até dia 25:** Publicar no Onvio e notificar cliente
**Saída:** Balancete e DRE mensais publicados no Onvio, sem divergências de conciliação

## 5. Pontos de Controle de Qualidade
- [ ] Todos os documentos do período recebidos antes de iniciar lançamentos
- [ ] Débitos = Créditos em todos os lançamentos (Domínio valida automaticamente)
- [ ] Conciliação bancária: saldo do extrato = saldo contábil (diferença zero)
- [ ] Nenhuma conta em aberto no balancete sem justificativa
- [ ] Coord. CTB assina revisão antes da publicação no Onvio

## 6. Tratamento de Não Conformidades
| Situação | Ação imediata | Prazo |
|---|---|---|
| Cliente não enviou documentos até dia 5 | Cobrar via WhatsApp; escalar para Coord. CTB | 24h |
| Divergência na conciliação | Investigar lançamento a lançamento; não fechar sem resolver | 48h |
| Classificação contábil incorreta descoberta após fechamento | Estorno e reclassificação; notificar cliente; FOR-NC-01 | 5 dias |
| Onvio indisponível | Enviar por e-mail com aviso de sistema; repostar quando normalizar | 2h |

## 7. KPIs e Metas
| Indicador | Meta | Frequência |
|---|---|---|
| Fechamento até dia 25 do mês seguinte | 100% dos clientes | Mensal |
| Divergências de conciliação bancária | 0 no fechamento | Mensal |
| Reclassificações após fechamento | 0 | Mensal |
| Clientes com acesso ao Onvio atualizado | 100% | Mensal |

## 8. Registros Obrigatórios
| Documento | Onde salvar | Retenção |
|---|---|---|
| Balancetes mensais (PDF) | Onvio + Google Drive / CTB / [Cliente] | 10 anos |
| DRE mensal (PDF) | Onvio + Google Drive / CTB / [Cliente] | 10 anos |
| Comprovantes de lançamentos | Domínio | 10 anos |
| Conciliações bancárias | Google Drive / CTB / Conciliações | 10 anos |
