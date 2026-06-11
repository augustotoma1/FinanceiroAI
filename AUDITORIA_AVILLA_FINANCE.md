# Auditoria de Segurança e Prontidão para Publicação — AV Finance (Avilla Finance)

> Portal de controle financeiro (contas a pagar/receber, mensalidades, cobranças e portal do responsável).
> Stack: **React 19 + TanStack Start/Router + Vite 7 + Supabase (Postgres/Auth/Storage) + Cloudflare Workers**.
> Data da auditoria: **2026-06-11** · Escopo: pacote `Avilla_Finance_4.zip`.

---

## 1. Resumo executivo

O projeto está, de modo geral, **bem construído do ponto de vista de segurança** — claramente acima da média de
projetos gerados por ferramentas low-code. Os fundamentos críticos para um sistema financeiro multi-tenant estão presentes:

- **Isolamento multi-tenant via RLS** (Row Level Security) ativo em **todas** as tabelas, com políticas escopadas por
  `organization_id = current_organization_id()`.
- **Endpoints de servidor protegidos** com verificação de papel (super admin / admin), validação de entrada com Zod,
  mensagens de erro genéricas e log de auditoria.
- **Chave de serviço (service role) nunca exposta ao cliente** — apenas a chave publishable/anon (que é pública por design).
- **Webhooks de e-mail com verificação de assinatura** e processamento de fila autenticado por service-role.

**Veredito:** o sistema **pode ser publicado**, mas recomendo resolver os itens **🔴 Altos** e **🟠 Médios** abaixo antes
do go-live (estimativa: 1–2 dias de trabalho). Não foram encontradas falhas que permitam, no estado final das migrations,
acesso de um inquilino (organização) aos dados de outro.

| Severidade | Qtde | Bloqueia publicação? |
|------------|------|----------------------|
| 🔴 Alto    | 2    | Recomendado resolver antes |
| 🟠 Médio   | 4    | Resolver antes / logo após |
| 🟡 Baixo   | 6    | Melhoria contínua |
| ✅ Pontos fortes | — | Já implementados |

---

## 2. Achados 🔴 ALTO

### 2.1. Configurações de Auth do Supabase não estão versionadas / verificadas
**Onde:** `supabase/config.toml` (contém apenas `project_id`).
**Risco:** A política de senha forte em `src/lib/password-policy.ts` é **apenas client-side** — pode ser contornada
chamando a API diretamente. As proteções reais (tamanho mínimo de senha, proteção contra senhas vazadas/HaveIBeenPwned,
expiração de OTP, confirmação de e-mail obrigatória, MFA e **lista de Redirect URLs permitidas**) vivem no painel do Supabase
e **não há evidência no repositório de que estejam configuradas**.
**Ação recomendada (antes de publicar):**
- Painel Supabase → Authentication → Policies: ativar **"Leaked password protection"** e definir **tamanho mínimo = 8**.
- Reduzir expiração de OTP/magic link para ≤ 15 min.
- Authentication → URL Configuration: restringir **Site URL** e **Redirect URLs** apenas a `https://avfinance.com.br`
  e domínios oficiais (evita open-redirect em fluxos de convite/recuperação).
- Rodar o **Security Advisor** do Supabase e tratar os avisos.

### 2.2. `bootstrap_admin()` permite escalonamento de privilégio em janela de borda
**Onde:** `supabase/migrations/20260503203926_*.sql`.
```sql
-- Qualquer usuário autenticado pode chamar; vira admin GLOBAL se não existir nenhum admin.
INSERT INTO public.user_roles(user_id, role) VALUES (uid, 'admin') ...
```
**Risco:** A função é concedida a `authenticated` e insere um papel `admin` **sem `organization_id`** (admin global, pois
`has_role` trata `organization_id IS NULL` como válido para qualquer org). Ela só bloqueia se **já existir algum admin no
sistema inteiro**. Em produção multi-tenant, se a tabela `user_roles` ficar sem nenhum admin (ex.: após exclusão de todas as
organizações, ou num estado inicial), **o próximo usuário autenticado qualquer** (inclusive um "responsável" do portal) pode
se tornar admin global chamando essa RPC.
**Ação recomendada:** após o bootstrap inicial, **remover/desabilitar** a função em produção:
```sql
DROP FUNCTION IF EXISTS public.bootstrap_admin();
-- ou, no mínimo: REVOKE EXECUTE ON FUNCTION public.bootstrap_admin() FROM authenticated;
```

---

## 3. Achados 🟠 MÉDIO

### 3.1. `.env` versionado e ausente do `.gitignore`
**Onde:** raiz do projeto. O `.gitignore` **não** lista `.env`.
**Situação atual:** o `.env` contém **apenas** `SUPABASE_URL` + chave **anon/publishable** (que é pública por design e já vai
embutida no bundle do cliente) — portanto **não há vazamento de segredo hoje**. O risco é de **higiene/futuro**: se alguém
adicionar `SUPABASE_SERVICE_ROLE_KEY`, `LOVABLE_API_KEY` ou `WHATSAPP_TOKEN` nesse `.env`, eles serão commitados.
**Ação recomendada:**
- Adicionar `.env` (e `.env.*` exceto `.env.example`) ao `.gitignore`.
- Criar `.env.example` documentando todas as variáveis (sem valores).
- Confirmar que os segredos de servidor (`SUPABASE_SERVICE_ROLE_KEY`, `LOVABLE_API_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`)
  estão configurados **apenas** como variáveis de ambiente no Cloudflare/Lovable — o código já os lê de `process.env` (correto).

### 3.2. Sem cabeçalhos de segurança HTTP (CSP, HSTS, X-Frame-Options)
**Risco:** Não há Content-Security-Policy nem cabeçalhos de proteção. A rota `/` renderiza o app principal
(`public/avfinance.html`, ~205 KB) dentro de um `<iframe>`, e esse app carrega bibliotecas de **CDN externo**
(`cdnjs.cloudflare.com`: Chart.js, XLSX) **sem Subresource Integrity (SRI)** — risco de comprometimento via supply-chain do CDN.
**Ação recomendada:**
- Adicionar SRI (`integrity=...`) às tags `<script>` de CDN **ou** auto-hospedar Chart.js/XLSX.
- Configurar via Cloudflare (headers ou `_headers`): `Content-Security-Policy`, `Strict-Transport-Security`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`.

### 3.3. Listagem de usuários limitada a 1000 (`listUsers({ perPage: 1000 })`)
**Onde:** `api/dev/organizations.*`, `api/portal.invite.ts`.
**Risco:** Buscas de usuário por e-mail iteram só a 1ª página (1000 usuários). Acima disso, verificações de
"usuário já existe" / convites podem **silenciosamente falhar**, permitindo duplicidade ou convite indevido. Aceitável no
início, mas é um risco latente de escala.
**Ação recomendada:** paginar de fato (loop por páginas) ou usar consulta direta por e-mail na tabela de auth/admin.

### 3.4. Validação de regras de negócio financeiras depende de trigger não auditado aqui
**Onde:** `cobrancas_validar()` (referenciada nas migrations).
**Observação:** existe uma trigger de validação de cobranças, mas o cálculo de juros/multa/desconto e a geração do payload PIX
(`gerarPayloadPix` em `portal.index.tsx`, com CRC16) ocorrem no **cliente**. Para um sistema de cobrança, recomendo validar/derivar
valores financeiros **no servidor/DB** (fonte de verdade), evitando manipulação via DevTools.
**Ação recomendada:** garantir que valores cobrados/baixados sejam recalculados/validados no banco (constraints + trigger),
não apenas no front.

---

## 4. Achados 🟡 BAIXO / melhorias

1. **Idioma do shell HTML:** `src/routes/__root.tsx` usa `<html lang="en">` enquanto o app é pt-BR. Trocar para `pt-BR` (acessibilidade/SEO).
2. **Nome de rota enganoso:** `/api/public/whatsapp/send` exige autenticação de admin (correto e seguro), mas o prefixo `public`
   sugere o contrário. Renomear para evitar confusão operacional.
3. **README vazio** (`# FinanceiroAI`, 14 bytes). Documentar: ordem das migrations, variáveis de ambiente, passos de deploy.
4. **Sem testes automatizados** de RLS/autorização. Recomendo testes que provem o isolamento entre organizações (um admin da
   Org A **não** lê dados da Org B) — é o controle mais crítico do produto.
5. **Duas migrations `email_infra` com timestamps muito próximos** (`20260527150125/150147/150317`) com conteúdo aparentemente
   repetido (REVOKE/GRANT idênticos). Revisar para evitar reaplicações redundantes.
6. **Dependências de pré-release em produção:** `nitro` `3.0.260603-beta` e versões muito recentes (React 19, Vite 7). Rodar
   `npm audit` no pipeline e fixar versões estáveis antes do go-live.

---

## 5. ✅ Pontos fortes confirmados (mantêm-se)

- **RLS** habilitado em todas as tabelas de domínio; políticas finais escopadas por `organization_id` (multi-tenant correto).
  As políticas iniciais fracas (`has_role` sem escopo) foram **substituídas** pela migration `20260528095019` e seguintes.
- **Funções `SECURITY DEFINER`** com `SET search_path = public` e `REVOKE` de `anon/public` — mitiga ataques de search_path e
  execução por anônimos (`has_role`, `is_super_admin`, `enqueue_email`, etc.).
- **Trigger `protect_profile_sensitive_fields`**: impede que um usuário altere o próprio `role`/`organization_id`
  (anti-escalonamento), permitindo exceção apenas para service-role e super admin.
- **`set_organization_id` + `current_organization_id`**: preenchimento automático e seguro do tenant nas inserções.
- **Endpoints admin** (`/api/dev/*`): `requireSuperAdmin` (via RPC `is_super_admin`), Zod, erros genéricos, **log de auditoria**.
- **`/api/portal/invite`**: guard de admin + **mitigação de timing** (piso de 600 ms) contra enumeração de usuários.
- **`/api/public/whatsapp/send`**: exige admin, normaliza telefone (E.164), CORS com allowlist; token do WhatsApp só no servidor.
- **Webhook de e-mail de auth**: verificação de assinatura/timestamp (`@lovable.dev/webhooks-js`); fila de e-mail processada
  apenas com **service-role** como Bearer; e-mails redigidos nos logs.
- **LGPD:** páginas de **Privacidade** e **Termos**, **banner de cookies** e fluxo de **descadastro** (unsubscribe) presentes;
  PII de e-mail (`email_send_log`) restrita a service-role via RLS.

---

## 6. Checklist de pré-publicação (ordenado)

- [ ] **(Alto)** Configurar Auth no painel Supabase: senha mínima 8, proteção de senha vazada, OTP curto, **Redirect URLs restritas**.
- [ ] **(Alto)** Rodar **Security Advisor** do Supabase e tratar avisos.
- [ ] **(Alto)** `DROP`/`REVOKE` em `bootstrap_admin()` após criar o primeiro super admin.
- [ ] **(Médio)** Adicionar `.env` ao `.gitignore` + criar `.env.example`; conferir segredos só em env do Cloudflare.
- [ ] **(Médio)** Cabeçalhos de segurança (CSP/HSTS/X-Frame-Options) + SRI ou auto-hospedagem das libs de CDN.
- [ ] **(Médio)** Paginação real em `listUsers`.
- [ ] **(Médio)** Validar valores financeiros/PIX no servidor (não confiar no cliente).
- [ ] **(Baixo)** `lang="pt-BR"`, README com deploy + variáveis, testes de isolamento de RLS, `npm audit`.
- [ ] **Operacional:** backups automáticos do Postgres ativos; monitorar a fila de e-mail (DLQ) e o `audit_log`.

---

*Auditoria de revisão de código e configuração. Não substitui um teste de intrusão (pentest) dinâmico contra o ambiente de
produção — recomendado após aplicar os itens acima.*
