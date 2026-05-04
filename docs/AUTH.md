# Autenticação e gestão de usuários

Este documento cobre autenticação (login email/senha, SSO Google),
gestão de status (ativo/desativado), reset de senha sem SMTP e
histórico de acessos.

## Visão geral

| Feature | Stack | Onde |
|---|---|---|
| Login email/senha | Better Auth (Next.js) | `/api/auth/sign-in/email` |
| Login Google SSO | Better Auth socialProviders | `/api/auth/sign-in/social` |
| Bootstrap admin | Hook em /login | `frontend/src/lib/bootstrap-admin-core.ts` |
| User status (ativo/desativado) | DB + databaseHook session.create.before | `auth.user.status` |
| Reset senha sem SMTP | Callback `sendResetPassword` persiste link | `auth.password_reset_pending` |
| Histórico de acesso | databaseHook session.create.after | `auth_login_event` |
| Rate limit login | Better Auth `rateLimit` | `frontend/src/lib/auth.ts` |

## Variáveis de ambiente

| Variável | Descrição | Obrigatória |
|---|---|---|
| `ADMIN_EMAIL` | Bootstrap: email do admin criado no primeiro login | sim no primeiro deploy |
| `ADMIN_PASSWORD` | Bootstrap: senha inicial | sim no primeiro deploy |
| `ADMIN_NAME` | Bootstrap: nome | não (default "Admin") |
| `BETTER_AUTH_SECRET` | Segredo HMAC pra cookies de sessão (≥32 chars em prod) | sim |
| `BETTER_AUTH_URL` | URL pública do frontend (ex: `https://chat.vsanexus.com`) | sim |
| `BETTER_AUTH_TRUSTED_ORIGINS` | CSV de origens confiáveis adicionais (LAN, IP) | opcional |
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth Client ID do Google Cloud (compartilhado com Calendar) | opcional (SSO + Calendar) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth Client Secret | opcional |

## SSO Google — config no Google Cloud Console

A stack reusa o **mesmo OAuth Client** entre Google Calendar (M5.a) e
SSO de login (E1.9). É só adicionar um redirect URI extra.

### Passo a passo

1. Abrir [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. Selecionar o OAuth 2.0 Client ID já usado pelo Calendar
3. Em **Authorized redirect URIs**, adicionar:
   - `https://chat.vsanexus.com/api/google-calendar/oauth/callback` (Calendar — já existe)
   - `https://chat.vsanexus.com/api/auth/callback/google` (**SSO — novo**)
4. Salvar

Não precisa redeploy — Google aceita os 2 URIs simultaneamente. As
mesmas `GOOGLE_OAUTH_CLIENT_ID/SECRET` no .env continuam valendo.

### Validação

1. Acessar `https://chat.vsanexus.com/login`
2. Aparece botão **"Entrar com Google"** (Better Auth detecta CLIENT_ID
   no env e o frontend mostra o botão)
3. Clicar → redirect Google → consent → callback → sessão criada
4. Conferir em `/settings/security/login-history`: row `login_success`
   com IP e User-Agent

### Vincular conta existente

Better Auth liga a conta Google ao user existente **se o email bater**.
Se admin já existe como `admin@vsanexus.com` (criado por bootstrap), e
o user faz login Google com a mesma conta Google `admin@vsanexus.com`,
a tabela `auth.account` ganha uma row a mais (`providerId='google'`)
sem criar user duplicado.

## User status (ativo / desativado)

Admin pode desativar membro pra bloquear acesso sem deletar (preserva
histórico, atendimentos, mensagens).

### Como funciona

1. Admin clica `XCircle` em `/companies/{id}/members`
2. Backend `PUT /api/empresas/{id}/membros/{user_id}/status` com `{status:"disabled"}`
3. Backend:
   - `UPDATE auth.user SET status='disabled'`
   - `DELETE FROM auth.session WHERE userId=<user>` (mata sessões ativas)
4. Próxima request do user expira; ao tentar logar de novo:
   - Better Auth chama `databaseHooks.session.create.before`
   - Hook lê status, vê `'disabled'`, lança Error → login falha
5. Reativar: clica `CheckCircle2` → `status='active'`. User precisa
   fazer login de novo (sessões antigas não voltam).

### Proteções

- Admin não pode desativar a si mesmo (evita lockout)
- Não pode desativar o último admin da empresa (paralelo a
  update_member_role e remove_member)
- Tentativa bloqueada vira row `session_blocked_disabled` em
  `auth_login_event` pra audit

## Reset de senha sem SMTP

A stack não tem SMTP configurado por padrão (M9 convite por email
cancelado). Reset é feito via "link manual":

1. Admin clica `KeyRound` em `/companies/{id}/members`
2. Server action `generateResetLinkAction(userId)`:
   - Resolve email do user
   - Chama `auth.api.requestPasswordReset({email})`
   - Better Auth gera token internamente e chama callback
     `sendResetPassword({user, url, token})` definido em
     `frontend/src/lib/auth.ts`
   - Callback **não envia email**: persiste a URL em
     `auth.password_reset_pending` (UPSERT, 1 row por user, expira em 1h)
3. Action lê `auth.password_reset_pending` pra retornar a URL
4. UI mostra `prompt()` com a URL pra admin copiar e mandar pelo
   canal que preferir (WhatsApp, Slack, email externo, etc)
5. User abre URL → reset normal do Better Auth → nova senha definida

### Habilitar email de verdade no futuro

Quando subir SMTP/Resend, basta substituir o callback
`sendResetPassword` pra mandar email em vez de persistir. UI continua
funcionando (admin ainda pode "gerar e enviar manualmente" se preferir
não esperar email).

## Histórico de acesso

Tabela `auth_login_event` armazena cada evento de auth com IP,
User-Agent, timestamp. Visualização em
`/settings/security/login-history`.

### Eventos cobertos

| event_type | Quando |
|---|---|
| `login_success` | Better Auth criou session com sucesso |
| `session_blocked_disabled` | Login falhou porque user.status=disabled |

### Eventos não cobertos (TODO em iteração futura)

- `login_failed` (credencial errada) — Better Auth não expõe hook
  nativo; precisa middleware HTTP em `/api/auth/sign-in/email`
- `logout` — não há hook session.delete; precisa custom endpoint
- `password_reset_requested` — capturável no callback `sendResetPassword`
- `password_changed` — capturável em `databaseHooks.user.update.after`

### Permissões

- **Superadmin** vê todos os eventos com filtros livres (user_id, email, type)
- **Não-superadmin** vê apenas próprio histórico (auto-filtrado por
  `requester_user_id`); filtro por email retorna 403

### Retenção

Padrão indefinido — recomendado cron mensal pra deletar registros
`>90 dias`. Ainda não implementado (TODO).

## Rate limit nas rotas auth

Better Auth nativo, configurado em `frontend/src/lib/auth.ts`:

| Rota | Limite | Janela |
|---|---|---|
| `/sign-in/email` | 5 tentativas | 15 min |
| `/sign-up/email` | 3 tentativas | 15 min |
| `/forget-password` | 3 chamadas | 1 hora |
| `/reset-password` | 5 chamadas | 1 hora |
| outras `/api/auth/*` | 30 req | 1 min |

Limite por IP. Excedido → HTTP 429.

## Referências

- Better Auth docs: https://better-auth.com
- Migration 022 — `rate_limit_bucket` (genérico, usado por admin
  endpoints; auth tem rate limit próprio do Better Auth)
- Migration 024 — `auth.user.status`
- Migration 025 — `auth.password_reset_pending`
- Migration 026 — `auth_login_event`
