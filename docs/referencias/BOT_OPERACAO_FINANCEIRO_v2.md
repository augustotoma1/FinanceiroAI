# Processo Operacional - Bot Financeiro AISATEC (v2)

Versao: 2.1  
Data: 15/02/2026  
Publico: Departamento Financeiro, Coordenacao Financeira, CFO

## 1. Objetivo

Padronizar o uso do bot financeiro no Telegram para:
1. Acompanhar contas a receber e contas a pagar com filtro de periodo.
2. Monitorar saldos, inadimplencia e status das integracoes.
3. Executar sincronizacao de clientes com governanca e rastreabilidade.
4. Medir risco de caixa e metas de performance com semaforo executivo.
5. Gerar evidencias operacionais para fechamento e tomada de decisao.

## 2. Escopo

Este processo cobre:
1. Uso dos comandos do bot no dia a dia.
2. Rotina diaria, semanal e mensal do financeiro.
3. Tratamento de erros funcionais e de integracao.
4. Regras de seguranca e registro de evidencias.
5. Indicadores estrategicos de risco de caixa e performance.

Nao cobre:
1. Ajustes de codigo.
2. Deploy de infraestrutura.
3. Alteracao de credenciais no servidor.

## 3. Papeis e Responsabilidades

1. Analista Financeiro
Executa comandos operacionais, registra evidencias e abre escalacao quando houver falha.

2. Coordenacao Financeira
Valida indicadores, acompanha SLAs de cobranca e aprova plano de acao.

3. CFO
Usa os resumos consolidados para decisao de caixa, risco e prioridade.

4. Responsavel Tecnico (TI/Automacao)
Atua em erros de integracao, token OAuth, infraestrutura e disponibilidade.

## 4. Pre-Requisitos

1. Usuario adicionado no Telegram do bot.
2. Integracoes ativas verificadas em `/status`.
3. Conta Azul autorizada.
4. Base de clientes sincronizada.
5. Time ciente dos formatos de periodo para `/receber` e `/pagar`.

## 5. Comandos Oficiais do Financeiro

1. `/status`
Confere saude geral: banco, IA, Conta Azul, Autentique, alertas automaticos e ultima sync.

2. `/sincronizar`
Forca sincronizacao manual de clientes quando necessario.

3. `/reconectar`
Envia o link de reconexão OAuth do Conta Azul para uso imediato quando o token expirar.

4. `/receber`
Consulta contas a receber. Se nao informar periodo no comando, o bot pergunta qual periodo usar.

5. `/pagar`
Consulta contas a pagar. Se nao informar periodo no comando, o bot pergunta qual periodo usar.

6. `/saldos`
Consulta saldos das contas financeiras.

7. `/inadimplencia`
Lista parcelas em atraso (prioriza as mais antigas).

8. `/dashboard`
Mostra KPIs de clientes e contratos.

9. `/cfo`
Mostra painel executivo com risco de caixa, metas, concentracao e tendencia 7 dias.

10. `/resumo_semanal`
Dispara o resumo semanal CFO sob demanda, sem esperar o agendamento.

11. `/cancelar`
Cancela fluxos pendentes (ex.: selecao de periodo ou criacao de contrato).

Observacao para `/sync_financeiro`:
1. Aceita periodo opcional como `/sync_financeiro 7d`, `/sync_financeiro mes` ou intervalo customizado.
2. Sem periodo informado, o bot pergunta o periodo antes de executar.

## 6. Filtros de Periodo (Obrigatorio para Receber/Pagar)

Os comandos `/receber` e `/pagar` aceitam:

1. Presets rapidos
`hoje`, `7d`, `30d`, `90d`, `mes`, `mes_passado`, `aberto`

2. Dias numericos
`7`, `30`, `90` (equivalente a proximos N dias)

3. Intervalo customizado
`AAAA-MM-DD AAAA-MM-DD`  
Exemplo: `2026-02-01 2026-02-28`

4. Formato BR
`DD/MM/AAAA DD/MM/AAAA`  
Exemplo: `13/02/2026 20/02/2026`

Exemplos praticos:
1. `/receber 30d`
2. `/pagar mes`
3. `/receber 2026-02-01 2026-02-28`
4. `/pagar` e depois responder `mes_passado`

## 7. Interpretacao dos Relatorios

### 7.1 Contas a Receber

O bot retorna:
1. `ATRASADAS`
2. `VENCEM HOJE`
3. `PROXIMOS 7 DIAS`
4. `DEMAIS PENDENTES`
5. `QUITADAS`
6. `Resumo a receber`

Regra de uso:
1. Priorizar cobranca em `ATRASADAS`.
2. Programar contatos preventivos para `VENCEM HOJE` e `PROXIMOS 7 DIAS`.
3. Conferir o `Resumo a receber` com meta semanal de caixa.

### 7.2 Contas a Pagar

O bot retorna:
1. `ATRASADAS`
2. `PENDENTES`
3. `PAGAS`
4. `Resumo a pagar`

Regra de uso:
1. Regularizar `ATRASADAS` com prioridade.
2. Planejar `PENDENTES` conforme previsao de caixa.
3. Confrontar `Resumo a pagar` com saldo disponivel.

### 7.3 Limite de exibicao

Se houver grande volume, o bot informa que exibiu ate 500 registros.  
Nessa situacao, quebrar a analise em periodos menores para visao completa.

### 7.4 Painel CFO (`/cfo`)

O painel executivo apresenta:
1. Risco de caixa (baixo/medio/alto)
2. Projecao de caixa em 15 dias
3. Concentracao dos 3 maiores clientes
4. Metas executivas (inadimplencia e concentracao)
5. Tendencia 7 dias (melhorando, estavel ou piorando)

Regra de uso:
1. Se tendencia estiver `PIORANDO`, abrir plano de acao no mesmo dia.
2. Se concentracao top 3 estiver acima da meta, priorizar diversificacao de carteira.
3. Se houver alerta de saldo zerado em todas as contas, validar saldos direto no Conta Azul.

## 8. Rotina Operacional Diaria (Padrao)

### 8.1 Abertura do dia (08:00-09:00)

1. Executar `/status`.
2. Se integracoes ok, executar `/receber hoje`.
3. Executar `/pagar hoje`.
4. Executar `/saldos`.
5. Registrar evidencias no controle interno.

### 8.2 Meio do dia (13:00-14:00)

1. Executar `/receber 7d`.
2. Revisar clientes em atraso e follow-up.
3. Se necessario, executar `/sincronizar` antes de nova rodada.

### 8.3 Fechamento do dia (17:00-18:00)

1. Executar `/receber mes`.
2. Executar `/pagar mes`.
3. Atualizar previsao de caixa do dia seguinte.
4. Consolidar pendencias para coordenacao/CFO.

## 9. Rotina Semanal e Mensal

### 9.1 Semanal (sexta-feira)

1. `/receber 30d`
2. `/pagar 30d`
3. `/inadimplencia`
4. Revisao de risco de concentracao e principais devedores
5. Validar recebimento do resumo semanal automatico CFO no Telegram

### 9.2 Mensal (fechamento)

1. `/receber mes_passado`
2. `/pagar mes_passado`
3. `/dashboard`
4. Validacao de consistencia com ERP/contabilidade

## 10. KPIs Estrategicos de Risco de Caixa

### 10.1 KPI 1 - Indice de Risco de Caixa

Formula base (score 0-100):
1. `risco_score = (peso_saldo * risco_saldo_15d) + (peso_atraso * risco_atraso) + (peso_concentracao * risco_concentracao)`
2. Pesos recomendados: saldo 0.4, atraso 0.35, concentracao 0.25.

Classificacao executiva:
1. `Baixo`: score < 35
2. `Medio`: score >= 35 e < 65
3. `Alto`: score >= 65

### 10.2 KPI 2 - Projecao de Saldo em 15 Dias

Formula:
1. `projecao_saldo_15d = saldo_atual + recebiveis_previstos_15d - pagamentos_previstos_15d`

Semaforo:
1. `Verde`: projecao >= 0
2. `Amarelo`: projecao < 0 e >= -5% do faturamento mensal
3. `Vermelho`: projecao < -5% do faturamento mensal

### 10.3 KPI 3 - Concentracao dos 3 Maiores Clientes

Formula:
1. `concentracao_top3 = (soma_aberto_top3_clientes / total_receber_aberto) * 100`

Semaforo:
1. `Verde`: <= 40%
2. `Amarelo`: > 40% e <= 60%
3. `Vermelho`: > 60%

## 11. KPIs de Performance com Meta Explicita

| KPI | Formula | Meta | Semaforo Verde | Semaforo Amarelo | Semaforo Vermelho |
|---|---|---|---|---|---|
| Inadimplencia sobre faturamento mensal | `total_atrasado / faturamento_mensal * 100` | `< 5%` | `< 5%` | `>= 5% e < 8%` | `>= 8%` |
| Tempo de resposta a incidente | media em horas | `< 4h` | `< 4h` | `>= 4h e < 8h` | `>= 8h` |
| Execucao da rotina diaria | `rotinas_executadas / rotinas_planejadas * 100` | `100%` | `100%` | `>= 90% e < 100%` | `< 90%` |
| Projecao de saldo 15d | ver secao 10.2 | `>= 0` | `>= 0` | `< 0 e >= -5%` | `< -5%` |
| Concentracao top 3 clientes | ver secao 10.3 | `<= 40%` | `<= 40%` | `> 40% e <= 60%` | `> 60%` |

## 12. Impacto Esperado na Empresa

1. Reducao da inadimplencia por priorizacao diaria de cobranca.
2. Aumento da previsibilidade de caixa com projeção de 15 dias.
3. Reducao de risco operacional com alertas e runbook estruturado.
4. Agilidade na decisao executiva com semaforo e metas claras.
5. Base de governanca para expansao e escala do modelo para outras unidades.

## 13. Alerta Diario Proativo (CFO)

O sistema possui alerta diario automatico no Telegram com:
1. Total atrasado.
2. Vencimentos do dia.
3. Proximos 7 dias.
4. Total em aberto.
5. Top 5 atrasadas.
6. Status preventivo do token Conta Azul (aviso de expiração).
7. Alerta de anomalia quando todas as contas ativas retornam saldo R$ 0,00.

Configuracao tecnica:
1. `TELEGRAM_ALERT_CHAT_IDS`
2. `TELEGRAM_ALERT_HOUR`
3. `TELEGRAM_ALERT_MINUTE`

Observacao:
Se nao houver chat configurado em variavel, o sistema tenta enviar para chats que ja interagiram com o bot.

## 14. Tratamento de Excecoes (Runbook)

### 14.1 Conta Azul expirada / invalid_grant

Sintoma:
`/status` mostra token expirado ou `/sincronizar` falha com invalid_grant.

Acao:
1. Escalar para responsavel tecnico.
2. Reautorizar via `/reconectar` no Telegram (preferencial).
3. Validar retorno em `/status`.
4. Validacao tecnica opcional via API (com autenticacao):
`curl -H "X-API-Key: <API_SECRET_KEY>" http://127.0.0.1:8000/api/auth/conta-azul/status`

### 14.2 Erro em receber/pagar por periodo invalido

Sintoma:
Bot responde formato invalido.

Acao:
1. Reenviar em formato aceito.
2. Preferir presets (`7d`, `mes`, `mes_passado`) para evitar erro manual.

### 14.3 Sem dados no resultado

Sintoma:
`Nenhuma conta encontrada`.

Acao:
1. Validar periodo escolhido.
2. Executar `/status`.
3. Executar `/sincronizar` se necessario.
4. Repetir comando com periodo mais amplo.

### 14.4 Bot indisponivel

Sintoma:
Sem resposta no Telegram.

Acao:
1. Escalar TI imediatamente.
2. TI validar servico `agent-financeiro` e endpoint `/health`.

### 14.5 Todos os saldos em R$ 0,00

Sintoma:
`/saldos` retorna todas as contas com `R$ 0,00` e alerta de validacao.

Acao:
1. Confirmar no Conta Azul se as contas possuem saldo no ambiente conectado.
2. Validar se a conciliacao/atualizacao de extrato foi executada no ERP.
3. Executar `/status` e checar se token esta ativo e sem alerta de expiração iminente.
4. Se persistir, escalar TI com print da resposta completa do comando.

## 15. Controle de Evidencias (Obrigatorio)

Registrar em planilha interna ou Notion:
1. Data/hora.
2. Usuario responsavel.
3. Comando executado.
4. Periodo utilizado.
5. Total a receber.
6. Total a pagar.
7. Total atrasado.
8. Risco de caixa (baixo, medio, alto).
9. Acao tomada.
10. Status final.

Retencao minima recomendada: 12 meses.

## 16. Politica de Seguranca

1. Nao compartilhar prints com dados sensiveis fora do canal corporativo.
2. Nao expor tokens, secrets ou URLs de administracao em grupos.
3. Restringir uso do bot a equipe autorizada.
4. Revisar acessos trimestralmente.

## 17. Checklist de Onboarding (Novo Integrante Financeiro)

1. Entrar no grupo/canal autorizado do bot.
2. Executar `/start` e `/ajuda`.
3. Treinar comandos: `/status`, `/receber`, `/pagar`, `/saldos`.
4. Simular 1 fluxo de excecao (periodo invalido e cancelamento).
5. Validar registro de evidencia no padrao do departamento.
6. Compreender semaforo dos KPIs e metas oficiais.

---

## Anexo A - Sequencia Recomendada para Operacao Diaria

1. `/status`
2. `/receber hoje`
3. `/pagar hoje`
4. `/saldos`
5. `/receber 7d`
6. `/inadimplencia`
7. Se token expirado: executar `/reconectar` e validar em `/status`
8. Atualizar semaforo dos KPIs no controle diario

## Anexo B - Padrao Minimo para Report ao CFO

1. Total em aberto.
2. Total atrasado.
3. Top 5 devedores atrasados.
4. Pagamentos criticos em ate 7 dias.
5. Risco de caixa (baixo, medio, alto).
6. Projecao de saldo em 15 dias.
7. Concentracao dos 3 maiores clientes.
8. Plano de acao (24h, 72h, 7 dias).
