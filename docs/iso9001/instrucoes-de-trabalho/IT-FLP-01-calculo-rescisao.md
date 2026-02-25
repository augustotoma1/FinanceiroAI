# IT-FLP-01 — Instrução de Trabalho: Cálculo de Rescisão Contratual
**Versão:** 1.0 | **Data:** 2026-02-24 | **Referência:** PR-FLP seção 4

## Objetivo
Passo a passo para calcular corretamente rescisões de funcionários, evitando erros nas verbas rescisórias.

## Quando usar
Toda vez que um cliente comunicar demissão ou pedido de demissão de funcionário.

## Dados necessários
- [ ] Data de admissão e demissão
- [ ] Tipo de rescisão: sem justa causa / com justa causa / pedido de demissão / acordo (§ 484-A CLT)
- [ ] Salário base + médias (horas extras, comissões, adicionais dos últimos 12 meses)
- [ ] Saldo de férias e abono pecuniário
- [ ] FGTS depositado e saldo na conta vinculada (via CAIXA FGTS app)

## Tabela de verbas por tipo de rescisão

| Verba | Sem justa causa | Pedido de demissão | Acordo |
|---|---|---|---|
| Saldo de salário | ✅ | ✅ | ✅ |
| Aviso prévio (trabalhado ou indenizado) | ✅ indenizado | ✅ trabalhado | 50% indenizado |
| 13º proporcional | ✅ | ✅ | ✅ |
| Férias vencidas + 1/3 | ✅ | ✅ | ✅ |
| Férias proporcionais + 1/3 | ✅ | ✅ | ✅ |
| Multa FGTS 40% | ✅ | ❌ | 20% |
| FGTS mês da rescisão | ✅ | ✅ | ✅ |
| Seguro-desemprego | ✅ (≥ 12 meses) | ❌ | ❌ |

## Cálculo passo a passo no Domínio
1. Acessar módulo **Rescisão** no Domínio
2. Selecionar funcionário e informar data e tipo de rescisão
3. Domínio calcula automaticamente; **VERIFICAR** manualmente:
   - Aviso prévio proporcional: 30 dias + 3 dias por ano trabalhado (máximo 60 dias adicionais = 90 dias total)
   - Férias proporcionais: (meses trabalhados no período aquisitivo / 12) × 30 dias
   - Média de horas extras: soma das horas extras dos últimos 12 meses / 12
4. Comparar resultado do Domínio com cálculo manual dos 3 itens acima
5. Se diferença > R$10: investigar antes de gerar o TRCT

## Validação final
- [ ] TRCT gerado com assinatura digital do funcionário via Autentique
- [ ] Guia de multa FGTS (se aplicável) gerada e enviada ao cliente
- [ ] Baixa do funcionário no eSocial realizada (prazo: até o 1º dia após rescisão)
