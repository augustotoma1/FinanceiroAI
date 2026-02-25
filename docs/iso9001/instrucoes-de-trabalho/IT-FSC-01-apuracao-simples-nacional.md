# IT-FSC-01 — Instrução de Trabalho: Apuração Simples Nacional (DAS)
**Versão:** 1.0 | **Data:** 2026-02-24 | **Referência:** PR-FSC seção 4

## Objetivo
Passo a passo para apurar corretamente o DAS mensal de clientes no Simples Nacional, evitando erros de alíquota e base de cálculo.

## Quando usar
Todo mês, para cada cliente optante pelo Simples Nacional, até o vencimento do DAS (dia 20 do mês seguinte).

## Dados necessários
- [ ] Faturamento bruto do mês (Receita Bruta Mensal — RBM)
- [ ] Faturamento bruto dos últimos 12 meses (Receita Bruta dos Últimos 12 Meses — RB12)
- [ ] Anexo do Simples Nacional do cliente (I, II, III, IV ou V — verificar no CNPJ)
- [ ] Tabela Simples Nacional vigente (atualizar em janeiro de cada ano)

## Cálculo passo a passo

1. **Calcular RB12:** somar os 12 meses anteriores ao mês de apuração (não incluir o mês atual)
2. **Identificar faixa de tributação** na tabela do Anexo correspondente com base no RB12
3. **Calcular alíquota efetiva:**
   `Alíquota Efetiva = (RB12 × Alíquota Nominal − Parcela a Deduzir) / RB12`
4. **Calcular DAS:** `DAS = RBM × Alíquota Efetiva`
5. **Verificar no Domínio:** conferir se o cálculo do sistema coincide com o cálculo manual (diferença tolerada: até R$1,00 por arredondamento)

## Alertas importantes
- Se RB12 > R$4,8 milhões: cliente está no limite do Simples; alertar Coord. FSC para avaliar exclusão
- Se RB12 cresceu > 20% vs. mês anterior: verificar se houve lançamento incorreto antes de apurar
- Atividades de serviço de tecnologia: verificar se não há substituição tributária de ISS pelo município
- Verificar tabela vigente todo mês de janeiro — alíquotas do Simples são reajustadas anualmente

## Validação final
- [ ] DAS gerado no PGDAS-D com recibo de transmissão
- [ ] Guia DAS enviada ao cliente com data de vencimento destacada (dia 20)
- [ ] Recibo salvo em Google Drive / FSC / DAS / [Cliente] / [Ano-Mês]
- [ ] Valor do DAS registrado no Conta Azul do cliente (contas a pagar)
