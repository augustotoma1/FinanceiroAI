# IT-FSC-01 — Instrução de Trabalho: Apuração Simples Nacional (DAS)
**Versão:** 2.0 | **Data:** 2026-02-26 | **Atualização:** Base legal brasileira
**Referência:** PR-FSC seção 4

## Objetivo
Passo a passo para apurar corretamente o DAS mensal de clientes optantes pelo Simples Nacional, evitando erros de alíquota e base de cálculo, em conformidade com a LC 123/2006 e a Resolução CGSN 140/2018.

## Base Legal

| Legislação | Dispositivo | Aplicação |
|---|---|---|
| LC 123/2006 | Art. 3º | Limites de faturamento: ME até R$360 mil/ano; EPP até R$4,8 milhões/ano |
| LC 123/2006 | Art. 13 | Tributos abrangidos pelo Simples Nacional (IRPJ, CSLL, PIS, COFINS, IPI, ICMS, ISS, CPP) |
| LC 123/2006 | Art. 17-18 | Vedações à opção e alíquotas por anexo (I a V) |
| LC 123/2006 | Art. 21 | Recolhimento unificado via DAS até o dia 20 do mês subsequente |
| LC 123/2006 | Art. 30 | Exclusão do Simples por excesso de receita |
| LC 155/2016 | Art. 1º | Alteração das faixas de tributação: 6 faixas por anexo com parcela a deduzir |
| Resolução CGSN 140/2018 | Art. 16-20 | Cálculo do valor devido: RBT12, alíquota nominal, parcela a deduzir, alíquota efetiva |
| Resolução CGSN 140/2018 | Art. 21-24 | Segregação de receitas por atividade e anexo |
| Resolução CGSN 140/2018 | Art. 25-26 | Fator R para serviços (Anexo III vs. V): Fator R = Folha 12 meses / RBT12 |
| Resolução CGSN 140/2018 | Art. 94-104 | Exclusão do Simples Nacional: causas, prazos e efeitos |
| Resolução CGSN 166/2022 | — | Atualizações procedimentais ao regulamento do Simples Nacional |
| LC 123/2006 | Art. 38-B | PGDAS-D: obrigatoriedade de declaração mensal no portal do Simples Nacional |

## Quando usar
Todo mês, para cada cliente optante pelo Simples Nacional, até o vencimento do DAS — **dia 20 do mês subsequente** ao período de apuração (LC 123/2006, Art. 21).

## Dados necessários
- [ ] Faturamento bruto do mês — **Receita Bruta Mensal (RBM)** segregada por atividade (Resolução CGSN 140/2018, Art. 21)
- [ ] Faturamento bruto acumulado dos últimos 12 meses — **Receita Bruta Total dos últimos 12 meses (RBT12)** (Resolução CGSN 140/2018, Art. 16)
- [ ] Anexo do Simples Nacional do cliente (I, II, III, IV ou V) conforme CNAE — verificar no cartão CNPJ (LC 123/2006, Art. 18)
- [ ] Tabela Simples Nacional vigente com 6 faixas por anexo (LC 155/2016)
- [ ] Folha de pagamento acumulada dos últimos 12 meses — necessária para cálculo do **Fator R** em serviços (Resolução CGSN 140/2018, Art. 26)
- [ ] Receitas com substituição tributária ou tributação monofásica, se houver (Resolução CGSN 140/2018, Art. 25)

## Cálculo passo a passo

### Passo 1 — Calcular RBT12 (Resolução CGSN 140/2018, Art. 16)
Somar os faturamentos brutos dos **12 meses anteriores** ao mês de apuração (não incluir o mês atual).

> **Atenção:** Se a empresa tem menos de 12 meses de atividade, utilizar receita proporcionalizada conforme Resolução CGSN 140/2018, Art. 16, §2º: `RBT12 proporcional = (Receita acumulada / nº meses em atividade) × 12`

### Passo 2 — Verificar limites de enquadramento (LC 123/2006, Art. 3º)
| Porte | Limite RBT12 | Ação se ultrapassar |
|---|---|---|
| MEI | R$81.000,00 | Desenquadrar para ME (comunicar ao cliente) |
| ME | R$360.000,00 | Reclassificar para EPP |
| EPP | R$4.800.000,00 | **Exclusão obrigatória do Simples Nacional** (LC 123/2006, Art. 30) |

> Se RBT12 > R$3.600.000,00: aplica-se o **sublimite estadual** para ICMS/ISS — estes tributos passam a ser recolhidos separadamente (LC 123/2006, Art. 19 e 20).

### Passo 3 — Identificar Anexo e faixa de tributação (LC 123/2006, Art. 18; LC 155/2016)
1. Consultar o CNAE principal e secundários do cliente
2. Enquadrar cada atividade no Anexo correspondente (I a V)
3. Para **serviços sujeitos ao Fator R** (atividades dos Anexos III e V):
   - Calcular Fator R = Folha de Salários últimos 12 meses / RBT12 (Resolução CGSN 140/2018, Art. 26)
   - Se Fator R ≥ 28%: tributa pelo **Anexo III** (alíquota menor)
   - Se Fator R < 28%: tributa pelo **Anexo V** (alíquota maior)
4. Identificar a faixa na tabela do Anexo correspondente com base no RBT12

### Passo 4 — Calcular alíquota efetiva (Resolução CGSN 140/2018, Art. 18)
```
Alíquota Efetiva = (RBT12 × Alíquota Nominal − Parcela a Deduzir) / RBT12
```
- A alíquota nominal e a parcela a deduzir são obtidas da tabela do Anexo/faixa identificados no Passo 3
- Para empresas com atividades em mais de um Anexo: calcular separadamente para cada segregação de receita (Resolução CGSN 140/2018, Art. 21-24)

### Passo 5 — Calcular valor do DAS (Resolução CGSN 140/2018, Art. 18, §1º)
```
DAS = RBM × Alíquota Efetiva
```
- Se houver receitas com **substituição tributária** de ICMS: excluir o percentual de ICMS da alíquota efetiva para essas receitas (Resolução CGSN 140/2018, Art. 25, §8º)
- Se houver receitas com **tributação monofásica** de PIS/COFINS: excluir os percentuais correspondentes

### Passo 6 — Conferir no Domínio e transmitir no PGDAS-D
1. Lançar dados no módulo de Simples Nacional do Domínio
2. **Conferir** se o cálculo do Domínio coincide com o cálculo manual (diferença tolerada: até R$1,00 por arredondamento)
3. Se divergência > R$1,00: investigar antes de transmitir — verificar se Fator R, anexo e faixa estão corretos
4. Acessar o **PGDAS-D** (portal do Simples Nacional) e transmitir a declaração (LC 123/2006, Art. 38-B)
5. Gerar a guia DAS com código de barras para pagamento

## Alertas importantes — Situações que exigem ação

| Situação | Base Legal | Ação |
|---|---|---|
| RBT12 > R$4.800.000,00 | LC 123/2006, Art. 3º, II e Art. 30 | **Exclusão obrigatória** — comunicar cliente e Coord. FSC imediatamente; preparar migração de regime |
| RBT12 > R$3.600.000,00 (sublimite) | LC 123/2006, Art. 19-20 | ICMS/ISS recolhidos por fora do DAS; recalcular DAS sem esses tributos |
| RBT12 cresceu > 20% vs. mês anterior | Resolução CGSN 140/2018, Art. 16 | Verificar se houve lançamento incorreto de receita antes de apurar |
| Fator R próximo de 28% (entre 25% e 31%) | Resolução CGSN 140/2018, Art. 26 | Alertar cliente sobre impacto tributário; simular ambos cenários (Anexo III vs. V) |
| Certificado digital A1 vencendo em < 30 dias | MP 2.200-2/2001 | Notificar cliente para renovação; sem certificado não transmite PGDAS-D |
| Atividade com substituição tributária | Resolução CGSN 140/2018, Art. 25 | Excluir parcela do ICMS/PIS/COFINS conforme o caso; não recolher em duplicidade |
| Empresa com menos de 13 meses de atividade | Resolução CGSN 140/2018, Art. 16, §2º | Usar RBT12 proporcionalizado |
| DAS vence em feriado/fim de semana | LC 123/2006, Art. 21 | Vencimento antecipa para último dia útil anterior |

## Validação final

- [ ] DAS gerado no **PGDAS-D** com recibo de transmissão (LC 123/2006, Art. 38-B)
- [ ] Alíquota efetiva calculada confere com tabela do Anexo vigente (LC 155/2016)
- [ ] Fator R calculado e documentado, se aplicável (Resolução CGSN 140/2018, Art. 26)
- [ ] Receitas segregadas corretamente por atividade/anexo (Resolução CGSN 140/2018, Art. 21)
- [ ] Substituição tributária e monofásico tratados, se aplicável (Resolução CGSN 140/2018, Art. 25)
- [ ] Guia DAS enviada ao cliente com data de vencimento destacada — **dia 20** (LC 123/2006, Art. 21)
- [ ] Recibo de transmissão salvo em Google Drive / FSC / DAS / [Cliente] / [Ano-Mês]
- [ ] Valor do DAS registrado no Conta Azul do cliente (contas a pagar)
- [ ] Limites de faturamento verificados — ME (R$360 mil), EPP (R$4,8 mi), sublimite (R$3,6 mi)

## Registros Obrigatórios

| Documento | Onde salvar | Retenção | Fundamentação |
|---|---|---|---|
| Recibo PGDAS-D | Google Drive / FSC / DAS / [Cliente] | 5 anos | LC 123/2006, Art. 38-B; CTN Art. 173 |
| Guia DAS (PDF) | Google Drive / FSC / DAS / [Cliente] | 5 anos | Resolução CGSN 140/2018, Art. 16 |
| Memória de cálculo (RBT12, Fator R, alíquota efetiva) | Google Drive / FSC / DAS / [Cliente] | 5 anos | Resolução CGSN 140/2018, Art. 18 |
| Comprovante de pagamento do DAS | Conta Azul + Google Drive | 5 anos | CTN Art. 156, I (extinção do crédito tributário) |
