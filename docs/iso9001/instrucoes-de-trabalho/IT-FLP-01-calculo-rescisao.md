# IT-FLP-01 — Instrução de Trabalho: Cálculo de Rescisão Contratual
**Versão:** 2.0 | **Data:** 2026-02-26 | **Atualização:** Base legal brasileira
**Referência:** PR-FLP seção 4

## Objetivo

Passo a passo para calcular corretamente rescisões de funcionários, evitando erros nas verbas rescisórias, em conformidade com a legislação trabalhista brasileira vigente.

### Base Legal

- **CLT (Decreto-Lei 5.452/1943) Art. 477-486** — Rescisão do contrato de trabalho, prazos, verbas rescisórias, TRCT
- **CLT Art. 484-A** — Demissão por acordo entre empregado e empregador (Reforma Trabalhista — Lei 13.467/2017)
- **Lei 8.036/1990 Art. 18** — Multa rescisória do FGTS (40% ou 20% conforme modalidade)
- **Lei 12.506/2011** — Aviso prévio proporcional ao tempo de serviço
- **Portaria MTP 671/2021 Art. 31-51** — TRCT, homologação e formalidades rescisórias
- **IN RFB 2.110/2022** — Contribuição previdenciária incidente sobre verbas rescisórias
- **Resolução CGSN 140/2018 Art. 64** — FGTS para empresas do Simples Nacional
- **Lei 7.998/1990** — Seguro-desemprego (requisitos e habilitação)
- **Súmula 305 TST** — Homologação de rescisão e quitação

## Quando usar

Toda vez que um cliente comunicar demissão ou pedido de demissão de funcionário, independentemente da modalidade de rescisão (CLT Art. 477).

**Prazo legal para pagamento das verbas rescisórias:** até 10 dias corridos contados do término do contrato (CLT Art. 477 §6º, com redação da Lei 13.467/2017).

**Multa por atraso:** salário do empregado como penalidade (CLT Art. 477 §8º).

## Dados necessários

| Dado | Fonte | Base Legal |
|---|---|---|
| Data de admissão e demissão | CTPS / Domínio | CLT Art. 29 |
| Tipo de rescisão | Comunicado do cliente | CLT Art. 477-484-A |
| Salário base + médias (HE, comissões, adicionais — últimos 12 meses) | Domínio / folhas anteriores | CLT Art. 457 §1º |
| Saldo de férias e abono pecuniário | Domínio | CLT Art. 129-145 |
| FGTS depositado e saldo na conta vinculada | Conectividade Social / CAIXA | Lei 8.036/1990 Art. 18 |
| Período aquisitivo em curso | Domínio | CLT Art. 130 |
| Aviso prévio proporcional (anos de serviço) | Domínio | Lei 12.506/2011 |

## Tabela de verbas por tipo de rescisão

| Verba | Base Legal | Sem justa causa | Pedido de demissão | Acordo (Art. 484-A) | Justa causa |
|---|---|---|---|---|---|
| Saldo de salário | CLT Art. 457 | ✅ | ✅ | ✅ | ✅ |
| Aviso prévio indenizado | CLT Art. 487 + Lei 12.506/2011 | ✅ integral | ❌ (trabalhado) | 50% do valor | ❌ |
| Aviso prévio proporcional | Lei 12.506/2011 Art. 1º | ✅ (+3 dias/ano, máx. 90 dias) | ❌ | 50% do proporcional | ❌ |
| 13º proporcional | Lei 4.090/1962 Art. 3º | ✅ | ✅ | ✅ | ❌ |
| Férias vencidas + 1/3 | CLT Art. 146 + CF Art. 7º XVII | ✅ | ✅ | ✅ | ✅ |
| Férias proporcionais + 1/3 | CLT Art. 146 parágrafo único | ✅ | ✅ | ✅ | ❌ |
| Multa FGTS | Lei 8.036/1990 Art. 18 | 40% | ❌ | 20% | ❌ |
| FGTS mês da rescisão | Lei 8.036/1990 Art. 15 | ✅ (8%) | ✅ (8%) | ✅ (8%) | ✅ (8%) |
| Saque FGTS | Lei 8.036/1990 Art. 20 | ✅ (total) | ❌ | ✅ (80% do saldo) | ❌ |
| Seguro-desemprego | Lei 7.998/1990 Art. 3º | ✅ (≥ 12 meses) | ❌ | ❌ | ❌ |

## Cálculos específicos com fundamentação legal

### Aviso prévio proporcional (Lei 12.506/2011)

```
Dias de aviso = 30 + (3 × anos completos de serviço)
Mínimo: 30 dias | Máximo: 90 dias (30 + 60)
```

**Exemplo:** funcionário com 5 anos → 30 + (3 × 5) = 45 dias de aviso prévio.

Na demissão por acordo (CLT Art. 484-A): aviso prévio indenizado é devido pela metade.

### Férias proporcionais (CLT Art. 130 + Art. 146)

```
Férias proporcionais = (meses trabalhados no período aquisitivo / 12) × 30 dias
Adicional constitucional = valor das férias / 3 (CF Art. 7º, XVII)
```

**Atenção:** considerar mês trabalhado o período ≥ 15 dias (CLT Art. 146 c/c Súmula 171 TST).

### Média de variáveis (CLT Art. 457 §1º)

```
Média de horas extras = soma das HE dos últimos 12 meses / 12
Média de comissões = soma das comissões dos últimos 12 meses / 12
```

As médias integram: aviso prévio, 13º e férias (CLT Art. 457 + Súmula 45 TST).

### Multa do FGTS (Lei 8.036/1990 Art. 18)

```
Sem justa causa: 40% sobre o total de depósitos FGTS + remuneração/JAM
Acordo (Art. 484-A): 20% sobre o total de depósitos FGTS
```

**Simples Nacional:** empresas optantes recolhem FGTS rescisório via GRRF conforme Resolução CGSN 140/2018 Art. 64 — a alíquota de 8% do FGTS mensal é mantida, não sendo incluída na guia DAS.

### Contribuição previdenciária na rescisão (IN RFB 2.110/2022)

Verbas **com** incidência de INSS: saldo de salário, 13º proporcional, aviso prévio indenizado (conforme IN RFB vigente), médias de variáveis.

Verbas **sem** incidência de INSS: férias indenizadas + 1/3, multa FGTS, multa do Art. 477 §8º CLT.

## Cálculo passo a passo no Domínio

1. Acessar módulo **Rescisão** no Domínio
2. Selecionar funcionário e informar data e tipo de rescisão (CLT Art. 477)
3. Domínio calcula automaticamente; **VERIFICAR** manualmente:
   - Aviso prévio proporcional conforme Lei 12.506/2011 (30 + 3 dias/ano)
   - Férias proporcionais conforme CLT Art. 130 + Art. 146
   - Média de horas extras conforme CLT Art. 457 §1º
   - Incidência de INSS conforme IN RFB 2.110/2022
4. Comparar resultado do Domínio com cálculo manual dos 4 itens acima
5. Se diferença > R$10: investigar antes de gerar o TRCT
6. Verificar enquadramento da multa FGTS: 40% (sem justa causa) ou 20% (acordo) conforme Lei 8.036/1990 Art. 18

## TRCT — Termo de Rescisão do Contrato de Trabalho

O TRCT deve conter todas as informações exigidas pela Portaria MTP 671/2021 Art. 31-51:

- [ ] Dados do empregador (CNPJ, razão social)
- [ ] Dados do empregado (CPF, CTPS, PIS)
- [ ] Causa do afastamento (código conforme tabela eSocial)
- [ ] Discriminação de cada verba paga e respectivo valor
- [ ] Data de admissão e data de afastamento
- [ ] Aviso prévio (tipo e duração)
- [ ] Valor líquido a receber

**Prazo para pagamento:** até 10 dias corridos do término do contrato (CLT Art. 477 §6º).

**Homologação:** desde a Reforma Trabalhista (Lei 13.467/2017), não é mais obrigatória no sindicato, independentemente do tempo de serviço. Porém, o empregado pode solicitar assistência sindical (CLT Art. 477 §7º).

## Validação final

| Verificação | Base Legal | Status |
|---|---|---|
| TRCT gerado com todas as informações obrigatórias | Portaria MTP 671/2021 Art. 31-51 | ☐ |
| TRCT assinado digitalmente via Autentique | MP 2.200-2/2001 (validade jurídica assinatura digital) | ☐ |
| Guia de multa FGTS (GRRF) gerada (se aplicável) | Lei 8.036/1990 Art. 18 | ☐ |
| GRRF enviada ao cliente com data de vencimento | Lei 8.036/1990 Art. 18 §1º | ☐ |
| Contribuição previdenciária calculada corretamente | IN RFB 2.110/2022 | ☐ |
| Baixa do funcionário no eSocial realizada | Decreto 8.373/2014 — Evento S-2299 (desligamento) | ☐ |
| Prazo de pagamento conferido (até 10 dias corridos) | CLT Art. 477 §6º | ☐ |
| Chave de conectividade social para saque FGTS | Lei 8.036/1990 Art. 20 | ☐ |
| Guias de seguro-desemprego entregues (se aplicável) | Lei 7.998/1990 Art. 3º-4º | ☐ |

## Registros obrigatórios

| Documento | Onde salvar | Retenção | Base Legal |
|---|---|---|---|
| TRCT assinado (PDF Autentique) | Domínio + Google Drive / FLP / [Cliente] | 10 anos | Portaria MTP 671/2021 Art. 51 |
| GRRF — Guia de multa FGTS | Google Drive / FLP / Guias / [Cliente] | 10 anos | Lei 8.036/1990 Art. 23 §5º |
| Comprovante de pagamento das verbas | Google Drive / FLP / [Cliente] | 10 anos | CLT Art. 477 |
| Recibo de entrega do seguro-desemprego | Google Drive / FLP / [Cliente] | 5 anos | Lei 7.998/1990 |
| Evento S-2299 (eSocial) — recibo | Domínio | 10 anos | Decreto 8.373/2014 |
