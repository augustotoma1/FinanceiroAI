# IT-SOC-01 — Instrução de Trabalho: Abertura de Empresa (Fluxo Detalhado)
**Versão:** 1.0 | **Data:** 2026-02-24 | **Referência:** PR-SOC seção 4

## Objetivo
Roteiro detalhado para abertura de empresa, com sequência correta de protocolos nos órgãos públicos, evitando retrabalho por protocolo fora de ordem.

## Quando usar
Toda vez que um cliente solicitar abertura de empresa (LTDA, SLU, MEI ou SA).

## Sequência obrigatória de protocolos

### Etapa 1 — Junta Comercial (ou Cartório para SS)
- **Portal:** gov.br/empresas-e-negocios (Integrador Estadual)
- **Pré-requisito:** Documentos dos sócios + endereço da sede
- **Documentos:** RG/CPF sócios, comprovante endereço sócios, comprovante sede (contrato de locação ou declaração)
- **Resultado:** **NIRE** (Número de Identificação do Registro de Empresa)
- **Prazo médio:** 3–5 dias úteis

### Etapa 2 — CNPJ (Receita Federal)
- **Portal:** gov.br/cnpj
- **Pré-requisito:** NIRE da Junta (**não protocolar sem NIRE**)
- **Documentos:** dados do contrato social, NIRE, dados dos sócios
- **Resultado:** **CNPJ** ativo
- **Prazo:** imediato (automático para a maioria dos CNAEs)

### Etapa 3 — Inscrição Estadual (SEFAZ) — se atividade comercial/industrial
- **Portal:** SEFAZ do estado (varia por UF)
- **Pré-requisito:** CNPJ ativo (**não protocolar sem CNPJ**)
- **Documentos:** CNPJ, contrato social, comprovante de endereço
- **Resultado:** **IE** (Inscrição Estadual)
- **Prazo:** 3–10 dias úteis (varia por UF)
- **Atenção:** atividades apenas de serviços são frequentemente **isentas** de IE — confirmar antes de protocolar

### Etapa 4 — Inscrição Municipal / ISS e Alvará (Prefeitura)
- **Portal:** portal da Prefeitura do município
- **Pré-requisito:** CNPJ ativo; IE obtida ou confirmação de isenta
- **Documentos:** CNPJ, contrato social, laudo sanitário (se exigido pela atividade), ART (se exigido)
- **Resultado:** **Inscrição Municipal** + **Alvará de Funcionamento**
- **Prazo:** 5–15 dias úteis (varia muito por município)

### Etapa 5 — Simples Nacional (se aplicável)
- **Portal:** simples.receita.fazenda.gov.br
- **Pré-requisito:** CNPJ ativo + situação regular na Receita Federal e FGTS
- **Prazo crítico:** até o **último dia útil do mês de abertura** para valer naquele mês
- **Atenção:** se perder o prazo, opção só pode ser feita em **janeiro do ano seguinte**
- Verificar se a atividade (CNAE) é vedada ao Simples antes de optar

## Checklist de encerramento (confirmar antes de entregar ao cliente)
- [ ] CNPJ ativo e sem pendências na Receita Federal
- [ ] IE obtida (ou "isenta" confirmado por escrito)
- [ ] Alvará de Funcionamento emitido
- [ ] Opção pelo Simples Nacional confirmada (ou outro regime configurado no Domínio)
- [ ] Cliente cadastrado no **SIEG** (captura de NFs)
- [ ] Cliente cadastrado no **Domínio** (contabilidade e folha)
- [ ] Cliente cadastrado no **Conta Azul** (financeiro)
- [ ] Cliente incluído na **planilha de controle** da SATEC
- [ ] Reunião de onboarding realizada com Coords. **FLP, CTB, FSC e ATD**
- [ ] Kit de boas-vindas enviado ao cliente via Autentique (prazos, contatos, checklists)
