# Processo Operacional - Bot Financeiro AISATEC

Versao: 1.0  
Data: 14/02/2026  
Publico: Departamento Financeiro, Coordenacao Financeira, CFO

## 1. Objetivo

Padronizar o uso do bot financeiro no Telegram para:
1. Acompanhar contas a receber e contas a pagar com filtro de periodo.
2. Monitorar saldos, inadimplencia e status das integracoes.
3. Executar sincronizacao de clientes com governanca e rastreabilidade.
4. Gerar evidencias operacionais para fechamento e tomada de decisao.

## 2. Escopo

Este processo cobre:
1. Uso dos comandos do bot no dia a dia.
2. Rotina diaria, semanal e mensal do financeiro.
3. Tratamento de erros funcionais e de integracao.
4. Regras de seguranca e registro de evidencias.

Nao cobre:
1. Ajustes de codigo.
2. Deploy de infraestrutura.
3. Alteracao de credenciais no servidor.

## 3. Papeis e Responsabilidades

1. Analista Financeiro
Executa os comandos operacionais, registra evidencias e abre escalacao quando houver falha.

2. Coordenacao Financeira
Valida os indicadores, acompanha SLAs de cobranca e aprova plano de acao.

3. CFO
Usa os resumos consolidados para decisao e priorizacao de caixa.

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
Confere saude geral: banco, IA, Conta Azul, Autentique, alerta diario e ultima sync.

2. `/sincronizar`
Forca sincronizacao manual de clientes quando necessario.

3. `/receber`
Consulta contas a receber. Se nao informar periodo no comando, o bot pergunta qual periodo usar.

4. `/pagar`
Consulta contas a pagar. Se nao informar periodo no comando, o bot pergunta qual periodo usar.

5. `/saldos`
Consulta saldos das contas financeiras.

6. `/inadimplencia`
Lista parcelas em atraso (prioriza as mais antigas).

7. `/dashboard`
Mostra KPIs de clientes e contratos.

8. `/cancelar`
Cancela fluxos pendentes (ex.: selecao de periodo ou criacao de contrato).

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
3. Conferir o `Resumo a receber` com a meta de caixa da semana.

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

### 9.2 Mensal (fechamento)

1. `/receber mes_passado`
2. `/pagar mes_passado`
3. `/dashboard`
4. Validacao de consistencia com ERP/contabilidade

## 10. Alerta Diario Proativo (CFO)

O sistema possui alerta diario automatico no Telegram com:
1. Total atrasado
2. Vencimentos do dia
3. Proximos 7 dias
4. Total em aberto
5. Top 5 atrasadas

Configuracao tecnica:
1. `TELEGRAM_ALERT_CHAT_IDS`
2. `TELEGRAM_ALERT_HOUR`
3. `TELEGRAM_ALERT_MINUTE`

Observacao:
Se nao houver chat configurado em variavel, o sistema tenta enviar para chats que ja interagiram com o bot.

## 11. Tratamento de Excecoes (Runbook)

### 11.1 Conta Azul expirada / invalid_grant

Sintoma:
`/status` mostra token expirado ou `/sincronizar` falha com invalid_grant.

Acao:
1. Escalar para responsavel tecnico.
2. Reautorizar via `GET /api/auth/conta-azul/authorize`.
3. Validar retorno em `/status`.

### 11.2 Erro em receber/pagar por periodo invalido

Sintoma:
Bot responde formato invalido.

Acao:
1. Reenviar em formato aceito.
2. Preferir presets (`7d`, `mes`, `mes_passado`) para evitar erro manual.

### 11.3 Sem dados no resultado

Sintoma:
`Nenhuma conta encontrada`.

Acao:
1. Validar periodo escolhido.
2. Executar `/status`.
3. Executar `/sincronizar` se necessario.
4. Repetir comando com periodo mais amplo.

### 11.4 Bot indisponivel

Sintoma:
Sem resposta no Telegram.

Acao:
1. Escalar TI imediatamente.
2. TI validar servico `agent-financeiro` e endpoint `/health`.

## 12. Controle de Evidencias (Obrigatorio)

Registrar em planilha interna ou Notion:
1. Data/hora
2. Usuario responsavel
3. Comando executado
4. Periodo utilizado
5. Total a receber
6. Total a pagar
7. Total atrasado
8. Acao tomada
9. Status final

Retencao minima recomendada: 12 meses.

## 13. Politica de Seguranca

1. Nao compartilhar prints com dados sensiveis fora do canal corporativo.
2. Nao expor tokens, secrets ou URLs de administracao em grupos.
3. Restringir uso do bot a equipe autorizada.
4. Revisar acessos trimestralmente.

## 14. Checklist de Onboarding (Novo Integrante Financeiro)

1. Entrar no grupo/canal autorizado do bot.
2. Executar `/start` e `/ajuda`.
3. Treinar comandos: `/status`, `/receber`, `/pagar`, `/saldos`.
4. Simular 1 fluxo de excecao (periodo invalido e cancelamento).
5. Validar registro de evidencia no padrao do departamento.

---

## Anexo A - Sequencia Recomendada para Operacao Diaria

1. `/status`
2. `/receber hoje`
3. `/pagar hoje`
4. `/saldos`
5. `/receber 7d`
6. `/inadimplencia`

## Anexo B - Padrao Minimo para Report ao CFO

1. Total em aberto
2. Total atrasado
3. Top 5 devedores atrasados
4. Pagamentos criticos em ate 7 dias
5. Risco operacional do dia (baixo, medio, alto)
