# AV Finance — Observações e Padrões de Segurança (Knowledge do Lovable)

> Como importar: copie todo o conteúdo deste arquivo e cole na **Base de Conhecimento (Knowledge / Project Context)**
> do Lovable, ou em **Settings → Knowledge**. Assim o Lovable trata estas regras como contexto permanente do projeto
> e as respeita em todas as gerações futuras de código.
>
> Origem: auditoria de segurança de 2026-06-11.

---

## Contexto do projeto

AV Finance (Avilla Finance) é um **portal financeiro multi-tenant** (contas a pagar/receber, mensalidades, cobranças,
PIX e portal do responsável). Stack: **React 19 + TanStack Start/Router + Vite 7 + Supabase (Postgres/Auth/Storage) +
Cloudflare Workers**. Há três papéis: `super_admin` (área `/desenvolvedor`), `admin` (gestor da organização) e
`responsavel` (portal do cliente). O isolamento entre organizações é feito por **RLS no Supabase**, escopado por
`organization_id = current_organization_id()`.

---

## Regras invioláveis (NUNCA quebrar ao gerar código)

1. **RLS sempre ativo.** Toda tabela nova de domínio deve ter `ENABLE ROW LEVEL SECURITY` e políticas escopadas por
   `organization_id = public.current_organization_id()`. Nunca criar política baseada só em `has_role(...)` sem filtrar
   o `organization_id` da linha — isso vaza dados entre organizações.
2. **Service role só no servidor.** A `SUPABASE_SERVICE_ROLE_KEY` e o cliente `supabaseAdmin` (`client.server.ts`) nunca
   podem aparecer em código de cliente nem no bundle. No front, usar apenas a chave **anon/publishable**.
3. **Segredos nunca no código nem no `.env` versionado.** `SERVICE_ROLE_KEY`, `LOVABLE_API_KEY`, `WHATSAPP_TOKEN`,
   `WHATSAPP_PHONE_ID` vivem apenas em variáveis de ambiente do servidor. Ler sempre de `process.env`.
4. **Endpoints sensíveis exigem autorização no servidor.** Todo handler em `src/routes/api/**` que altera dados deve
   validar o papel (`requireSuperAdmin` / `has_role`), validar a entrada com **Zod**, retornar **erros genéricos** e,
   quando alterar dados de organização, gravar **log de auditoria** (`writeAuditLog`).
5. **Funções `SECURITY DEFINER`** devem ter `SET search_path = public` e `REVOKE` de `anon`/`public`.
6. **Não confiar em valores financeiros vindos do cliente.** Cálculos de juros/multa/desconto e o valor do PIX devem ser
   validados/derivados no banco (constraints/triggers), não apenas no front.
7. **Usuário não pode alterar o próprio `role` ou `organization_id`.** A trigger `protect_profile_sensitive_fields`
   garante isso — não enfraquecer.

---

## Pendências de segurança a aplicar (backlog priorizado)

### 🔴 Alta
- **Remover `bootstrap_admin()`**: permite que qualquer usuário autenticado vire admin global quando não há nenhum admin.
  Criar migration que (após confirmar que já existe admin/super_admin) faça `REVOKE` + `DROP FUNCTION bootstrap_admin`.
- **Endurecer Auth no painel Supabase** (não é código): ativar proteção de senha vazada, senha mínima = 8, OTP ≤ 15 min,
  restringir Site URL e Redirect URLs aos domínios oficiais; rodar o Security Advisor.

### 🟠 Média
- **`.env`**: adicionar `.env`/`.env.*` ao `.gitignore` (exceto `.env.example`) e criar `.env.example` documentando todas
  as variáveis (separando públicas de secretas).
- **Cabeçalhos de segurança**: adicionar `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options`,
  `Referrer-Policy` e `X-Frame-Options`/`frame-ancestors`. No `public/avfinance.html`, adicionar **SRI** às libs de CDN
  (Chart.js, XLSX) ou auto-hospedá-las.
- **Paginação de `listUsers`**: substituir `listUsers({ page: 1, perPage: 1000 })` por busca paginada completa /
  consulta direta por e-mail (usar utilitário `findAuthUserByEmail`). Afeta `src/routes/api/dev/*` e `portal.invite.ts`.
- **Validação financeira no servidor** (ver regra inviolável nº 6).

### 🟡 Baixa
- `<html lang="en">` → `lang="pt-BR"` em `src/routes/__root.tsx`.
- Renomear `/api/public/whatsapp/send` para `/api/whatsapp/send` (o nome "public" engana; a rota exige admin).
- Criar `README.md` (stack, variáveis, ordem de migrations, deploy).
- Testes automatizados de isolamento RLS (admin da Org A não acessa dados da Org B; responsável só vê os próprios dados).
- Consolidar migrations `email_infra` duplicadas (`20260527150125/150147/150317`) de forma idempotente.
- Rodar `npm audit`; substituir pré-releases em produção (ex.: `nitro` beta) por versões estáveis.

---

## O que JÁ está correto (não regredir)

- RLS em todas as tabelas, escopado por `organization_id`; políticas fracas iniciais já substituídas (migration `20260528095019`+).
- Funções `SECURITY DEFINER` com `search_path` e `REVOKE` de anônimos.
- Trigger anti-escalonamento de `role`/`organization_id`; preenchimento automático de tenant (`set_organization_id`).
- Endpoints admin com `requireSuperAdmin`/`has_role` + Zod + erros genéricos + auditoria.
- `/api/portal/invite` com mitigação de timing (piso de 600 ms) contra enumeração de usuários.
- Webhook de e-mail com verificação de assinatura; fila processada só com service-role; e-mails redigidos nos logs.
- LGPD: páginas de Privacidade/Termos, banner de cookies, fluxo de descadastro; PII de e-mail restrita a service-role.
