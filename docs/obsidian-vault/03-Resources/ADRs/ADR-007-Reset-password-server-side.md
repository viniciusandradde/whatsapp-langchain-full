---
title: ADR-007 — Reset de senha gerado server-side (CSPRNG, sem email)
type: adr
status: aceito
priority: alta
created: 2026-05-16
updated: 2026-05-17
tags: [adr, auth, security, csprng, reset-password]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Compliance-LGPD
projeto_pai:
relacionados: [ADR-005-Better-Auth-em-schema-separado]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-007 — Reset de senha gerado server-side (CSPRNG, sem email)

## Status

Aceito (em produção desde commit `262f09c`).

## Contexto

Originalmente, Better Auth fluxo padrão é: user clica "esqueci senha" → SMTP envia link de reset → user define nova no link. Nexus não tem infra SMTP, então adaptamos:
- `sendResetPassword` callback persistia link em `auth.password_reset_pending` (1h TTL)
- Admin gerava link via UI e compartilhava manual (WhatsApp/Slack)

Funcionou, mas admin tinha que entender que "reset" significava "gerar link pra user definir nova senha". Cliente final achava confuso. Pediram: **admin define a senha direto, sem precisar de link**.

Primeira tentativa: modal com input "Digite a nova senha". User Vinicius rejeitou:
> "não é para fazer isso no frontend fazer como padrão de segurança via banco"

## Decisão

**Backend gera senha aleatória forte (CSPRNG)** e retorna **uma vez** pro frontend mostrar. Admin copia e compartilha pelo canal escolhido.

Sem input de senha em lugar nenhum da UI. Sem armazenamento da senha em plaintext em logs/audit (só hash bcrypt via Better Auth `updateUser`).

## Implementação

`frontend/src/app/companies/[id]/members/actions.ts::resetMemberPasswordAction`:
```ts
function generateSecurePassword(len = 16): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%&*";
  const arr = new Uint8Array(len);
  crypto.getRandomValues(arr); // Web Crypto API CSPRNG
  return Array.from(arr, (b) => chars[b % chars.length]).join("");
}
```

- Roda **Server Action** (server-side, mesmo Node Next)
- Usa `crypto.getRandomValues` (Web Crypto API) — não `Math.random()`
- Charset: 60 chars (sem confundíveis: O/0, I/l/1)
- Tamanho 16 → entropia ~94 bits (mais que suficiente pra uso humano)
- Modal mostra senha + botão copy + aviso "salve agora, não será mostrada de novo"

## Consequências

### Positivas
- **Admin não digita senha** — não tem como vazar via screenshot/teclado/clipboard que admin escolheu mal
- **Força garantida** — sempre 16 chars, charset amplo, CSPRNG
- **Sem dependência de SMTP** — funciona offline-grade
- **Audit trail** — `audit_governanca` registra "reset_password" mas sem o valor

### Negativas
- **Admin tem responsabilidade** de compartilhar senha pelo canal certo (WhatsApp, presencial). Se manda por email não cifrado, vaza
- **Senha aparece UMA VEZ** — se admin fecha modal sem copiar, precisa resetar de novo

## Alternativas consideradas

| Opção | Por que não |
|---|---|
| Admin digita nova senha | Rejeitado por user — risco de admin escolher fraca + UX de digitar 2x |
| Link de reset (fluxo Better Auth) | Funciona, mas user pediu "criar nova senha", não "gerar link" |
| SMTP + email com senha | Sem infra SMTP. Email plaintext com senha é antipattern |
| OAuth force-relogin | Não resolve — precisa ainda definir credencial |

## Relacionados

- [[ADR-005-Better-Auth-em-schema-separado]]
- [[02-Areas/Compliance-LGPD]]
- [[01-Projects/Governanca-RBAC-Frontend]]
- `frontend/src/app/companies/[id]/members/actions.ts`
