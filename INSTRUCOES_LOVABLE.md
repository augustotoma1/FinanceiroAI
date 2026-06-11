# Instruções para o Lovable — Correções de Segurança do AV Finance

> Como usar: copie cada bloco **"PROMPT PARA O LOVABLE"** e cole no chat do Lovable, um de cada vez, na ordem
> apresentada. Aguarde o Lovable aplicar e revise o diff antes de seguir para o próximo.
> Os itens marcados com 🖥️ **PAINEL** não são código — você mesmo faz no painel do Supabase/Cloudflare (instruções incluídas).
>
> Base: relatório `AUDITORIA_AVILLA_FINANCE.md`. Data: 2026-06-11.

---

## 🔴 PRIORIDADE ALTA (fazer antes de publicar)

### A1 — Remover a função `bootstrap_admin` (escalonamento de privilégio)

> **PROMPT PARA O LOVABLE:**
>
> Crie uma nova migration do Supabase que remova com segurança a função `public.bootstrap_admin`, pois ela
> permite que qualquer usuário autenticado vire admin global quando não existe nenhum admin no sistema.
> Antes de remover, garanta que já existe pelo menos um `super_admin`. A migration deve conter:
>
> ```sql
> -- Aborta se não houver nenhum admin/super_admin (evita travar o acesso)
> DO $$
> BEGIN
>   IF NOT EXISTS (SELECT 1 FROM public.user_roles WHERE role = 'admin')
>      AND NOT EXISTS (SELECT 1 FROM public.profiles WHERE role = 'super_admin') THEN
>     RAISE EXCEPTION 'Não remover bootstrap_admin: nenhum admin/super_admin existe ainda.';
>   END IF;
> END $$;
>
> REVOKE ALL ON FUNCTION public.bootstrap_admin() FROM authenticated, anon, public;
> DROP FUNCTION IF EXISTS public.bootstrap_admin();
> ```
>
> Verifique também que nenhum código do front-end chama `bootstrap_admin` (rpc). Se chamar, remova a chamada.

---

### A2 🖥️ PAINEL — Reforçar as configurações de autenticação do Supabase

Estas mudanças **não são código** — faça no painel (o Lovable não controla isso). No projeto Supabase `ohlkfkxobgimyccdapgy`:

1. **Authentication → Sign In / Providers → Password:**
   - Ativar **"Leaked password protection"** (verificação HaveIBeenPwned).
   - Definir **"Minimum password length" = 8**.
2. **Authentication → Sessions / Email:** reduzir a expiração de **OTP / magic link** para **≤ 15 minutos**.
3. **Authentication → URL Configuration:**
   - **Site URL** = `https://avfinance.com.br`.
   - **Redirect URLs**: deixar **apenas** os domínios oficiais (`https://avfinance.com.br/**` e o preview do Lovable).
     Remover wildcards abertos — isso evita open-redirect nos fluxos de convite/recuperação de senha.
4. **Advisors → Security Advisor:** rodar e tratar todos os avisos exibidos.

> Dica: você pode pedir ao Lovable depois — *"rode o Security Advisor do Supabase e me mostre os avisos"* — para conferir o resultado.

---

## 🟠 PRIORIDADE MÉDIA

### M1 — Proteger `.env` e documentar variáveis

> **PROMPT PARA O LOVABLE:**
>
> Atualize o `.gitignore` para ignorar arquivos de ambiente, adicionando estas linhas:
> ```
> .env
> .env.*
> !.env.example
> ```
> Em seguida, crie um arquivo `.env.example` na raiz, com TODAS as variáveis usadas no projeto, **sem valores reais**,
> apenas placeholders e um comentário indicando se é pública (cliente) ou secreta (apenas servidor):
> ```
> # Públicas (embutidas no bundle do cliente — podem ser commitadas)
> VITE_SUPABASE_URL=
> VITE_SUPABASE_PUBLISHABLE_KEY=
> VITE_SUPABASE_PROJECT_ID=
> SUPABASE_URL=
> SUPABASE_PUBLISHABLE_KEY=
> SUPABASE_PROJECT_ID=
> # Secretas (NUNCA commitar — configurar só no ambiente do servidor/Cloudflare)
> SUPABASE_SERVICE_ROLE_KEY=
> LOVABLE_API_KEY=
> WHATSAPP_TOKEN=
> WHATSAPP_PHONE_ID=
> ```
> Não remova o `.env` atual do funcionamento local, apenas pare de versioná-lo.

---

### M2 — Adicionar cabeçalhos de segurança HTTP e SRI nas libs de CDN

> **PROMPT PARA O LOVABLE:**
>
> 1. Adicione cabeçalhos de segurança em todas as respostas do app (via configuração do Cloudflare/TanStack Start).
>    Inclua: `Content-Security-Policy`, `Strict-Transport-Security` (HSTS), `X-Content-Type-Options: nosniff`,
>    `Referrer-Policy: strict-origin-when-cross-origin` e `X-Frame-Options`/`frame-ancestors` adequado ao iframe interno.
>    A CSP deve permitir `https://cdnjs.cloudflare.com` (scripts), `https://*.supabase.co` (connect) e o storage de logos.
> 2. No arquivo `public/avfinance.html`, as bibliotecas Chart.js e XLSX são carregadas via `cdnjs.cloudflare.com`
>    sem proteção de integridade. Adicione atributos **Subresource Integrity (`integrity` + `crossorigin="anonymous"`)**
>    às tags de script dessas libs, ou, preferencialmente, **auto-hospede** esses arquivos em `public/vendor/` e
>    aponte os scripts para os arquivos locais. Mantenha o comportamento de carregamento sob demanda já existente.

---

### M3 — Paginar a listagem de usuários do Supabase Auth

> **PROMPT PARA O LOVABLE:**
>
> Em todos os lugares que usam `supabaseAdmin.auth.admin.listUsers({ page: 1, perPage: 1000 })`
> (arquivos em `src/routes/api/dev/*` e `src/routes/api/portal.invite.ts`), substitua a busca de "página única"
> por uma **busca paginada completa** ou por uma consulta direta por e-mail, para que verificações de
> "usuário já existe" e convites não falhem silenciosamente quando houver mais de 1000 usuários.
> Crie uma função utilitária reutilizável (ex.: `findAuthUserByEmail(email)`) que itere as páginas até encontrar
> o usuário ou acabar a lista, e use-a nesses endpoints.

---

### M4 — Validar valores financeiros no servidor (não confiar no cliente)

> **PROMPT PARA O LOVABLE:**
>
> Hoje o cálculo de juros/multa/desconto e a geração do payload PIX (`gerarPayloadPix` em `src/routes/portal.index.tsx`)
> acontecem no cliente. Para um sistema de cobrança, os valores financeiros não podem ser confiáveis vindos do front.
> Faça o seguinte:
> 1. Garanta que a baixa/pagamento de uma cobrança (mudança de status para "pago", valor pago, juros, multa, desconto)
>    seja **calculada e validada no banco**, via trigger/constraint na tabela `cobrancas` (reforce a função `cobrancas_validar`),
>    de modo que valores enviados pelo cliente sejam recalculados ou rejeitados se inconsistentes.
> 2. Mantenha a geração de QR Code PIX no cliente apenas para exibição, mas garanta que o **valor** usado no payload
>    venha do registro de cobrança no banco, não de um campo editável pelo usuário.

---

## 🟡 PRIORIDADE BAIXA (melhorias)

### B1 — Corrigir idioma do HTML

> **PROMPT PARA O LOVABLE:**
>
> Em `src/routes/__root.tsx`, troque `<html lang="en">` por `<html lang="pt-BR">`, já que o app é em português.

### B2 — Renomear a rota de WhatsApp (nome enganoso)

> **PROMPT PARA O LOVABLE:**
>
> A rota `/api/public/whatsapp/send` exige autenticação de admin, mas o prefixo "public" sugere o contrário.
> Mova-a para `/api/whatsapp/send` (fora de "public"), atualizando o arquivo de rota e todas as chamadas no front.
> Mantenha exatamente a mesma lógica de autenticação, CORS e validação.

### B3 — Documentar o projeto (README)

> **PROMPT PARA O LOVABLE:**
>
> Crie um `README.md` completo descrevendo: o que é o AV Finance, a stack, a lista de variáveis de ambiente (referenciando
> o `.env.example`), como rodar localmente, a ordem de aplicação das migrations do Supabase e os passos de deploy no Cloudflare.

### B4 — Testes de isolamento entre organizações (RLS)

> **PROMPT PARA O LOVABLE:**
>
> Crie testes automatizados que provem o isolamento multi-tenant: dado um admin da Organização A, ele **não** deve
> conseguir ler nem alterar registros (alunos, responsáveis, cobranças, despesas) da Organização B. Cubra também o
> portal do responsável (um responsável só vê os próprios alunos/cobranças). Use o cliente Supabase autenticado como
> cada papel para validar as políticas RLS.

### B5 — Limpar migrations de e-mail duplicadas

> **PROMPT PARA O LOVABLE:**
>
> Existem migrations `email_infra` com timestamps muito próximos (`20260527150125`, `20260527150147`, `20260527150317`)
> com conteúdo aparentemente repetido (REVOKE/GRANT idênticos). Verifique se há duplicação real e, se houver,
> consolide de forma idempotente para evitar reaplicações redundantes — sem quebrar o histórico já aplicado em produção.

### B6 — Auditar dependências e fixar versões estáveis

> **PROMPT PARA O LOVABLE:**
>
> Rode uma auditoria de dependências (`npm audit`) e me mostre as vulnerabilidades. Avalie substituir pacotes em
> pré-release usados em produção, como `nitro` `3.0.260603-beta`, por versões estáveis, e fixe as versões críticas.

---

## Ordem sugerida de execução

1. **A1** (migration bootstrap_admin) → **A2** (painel Supabase)
2. **M1** (.env) → **M2** (headers/SRI) → **M3** (paginação) → **M4** (validação financeira)
3. **B1**–**B6** conforme disponibilidade.

Após aplicar A1–M4, peça ao Lovable para **rodar o Security Advisor do Supabase novamente** e confirme que não restam
avisos críticos antes de publicar.
