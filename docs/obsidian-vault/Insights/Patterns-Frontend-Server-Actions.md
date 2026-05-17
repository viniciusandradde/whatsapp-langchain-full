---
title: Pattern — Server Actions wrappers pra Client Components
type: insight
status: validado
priority: media
created: 2026-05-16
updated: 2026-05-17
tags: [pattern, frontend, next, server-actions]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: padrao-tecnico
area: Infra-Producao
projeto_pai:
relacionados: [Governanca-RBAC-Frontend]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Pattern — Server Actions wrappers pra Client Components

## Problema

`frontend/src/lib/api.ts::apiFetch` é **server-only**:
- Importa `next/headers` → cookies do request
- Importa `auth` (Better Auth) → escapa pro `pg` driver
- `pg` driver puro Node → quebra Turbopack quando bundleado pro browser

Client Component (`"use client"`) que importasse `lib/api.ts` quebrava o build:
```
Module not found: Can't resolve 'pg' → 'fs/net/tls'
```

## Solução validada

**Server Action wrappers** em arquivo `actions.ts` separado, dentro da pasta da feature:

```
companies/[id]/members/
├── members-list.tsx      ("use client" — só usa actions)
├── actions.ts            ("use server" — chama apiFetch)
└── page.tsx              (Server Component que renderiza members-list)
```

`actions.ts`:
```ts
"use server";
import { apiFetch } from "@/lib/api";

export async function loadMembersAction(empresaId: number) {
  return apiFetch(`/api/empresas/${empresaId}/membros`);
}

export async function changeMemberRoleAction(
  empresaId: number,
  userId: string,
  role: string,
) {
  return apiFetch(`/api/empresas/${empresaId}/membros/${userId}`, {
    method: "PATCH",
    body: { role },
  });
}
```

`members-list.tsx`:
```tsx
"use client";
import { loadMembersAction, changeMemberRoleAction } from "./actions";

export function MembersList({ empresaId }: { empresaId: number }) {
  const [members, setMembers] = useState([]);
  useEffect(() => {
    loadMembersAction(empresaId).then(setMembers);
  }, [empresaId]);
  // ...
}
```

## Vantagens

- Client Component fica **puro** (sem refs a `pg`/`auth`)
- Type-safe ponta a ponta (TS dos actions cruza pro client)
- Bundler não tenta compilar `pg` pro browser
- Erros são propagados via `throw new Error()` no action → catch no client
- Audit/log fica no server (sem expor lógica de auth)

## Quando NÃO usar

- Se precisa de streaming real-time → use Route Handler + SSE/WebSocket
- Se precisa cache HTTP agressivo → Route Handler com cache-control
- Pra dados estáticos → Server Component que passa props pro client

## Tradeoffs

- 1 round-trip extra (form post-like) vs fetch direto, mas vantagem em segurança vale
- Server Action signature precisa serializar args (sem funções, classes complexas)

## Adoção no Nexus

Padronizado em:
- `companies/[id]/members/actions.ts` — members CRUD + reset password
- `app/atendimento/actions.ts` — load atendentes online, transferir
- `app/companies/[id]/members/edit-permissions/actions.ts` — perfis/deptos
- TODO: aplicar nas outras telas que ainda importam `lib/api.ts` diretamente

## Relacionados

- [[01-Projects/Governanca-RBAC-Frontend]]
- [[02-Areas/Infra-Producao]]
