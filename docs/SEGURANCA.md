# Segurança — postura, achados e remediação

Documento de referência da postura de segurança do Chat Nexus. Consolida o **red team de 2026-09-16** (avaliação autorizada pelo dono sobre o código de produção) e serve de checklist vivo: conforme cada item for corrigido, marque o **Status**.

Método: 6 agentes de revisão em paralelo (um por domínio) + recon de infraestrutura na produção + `pip-audit` sobre o `uv.lock`. Achados de severidade **alta+** foram reverificados no código. Relatório datado de origem: `.planning/reports/20260916-red-team-seguranca.md`.

**Escopo coberto:** revisão estática de código + recon de infra + dependências. **NÃO coberto:** pentest dinâmico contra a instância em execução, fuzzing, e revisão dos workflows LangGraph em produção (placeholders já registrados à parte).

Placar em 2026-09-16: **2 críticos · 6 altos · 13 médios · 11 baixos/info · 30+ defesas corretas.**

---

## Severidade

| Nível | Significado |
|---|---|
| 🔴 Crítico | exploração direta, alto impacto |
| 🟠 Alto | exploração viável, impacto sério |
| 🟡 Médio | exige pré-condição ou impacto contido |
| ⚪ Baixo | defesa em profundidade / informativo |

---

## 🔴 Críticos

### C1 — Server Actions de reset de senha sem autenticação → account takeover cross-tenant
- **Domínio:** Auth/RBAC (frontend) · **Status:** ABERTO
- `frontend/src/app/companies/[id]/members/actions.ts` não tem **nenhuma** chamada de `getSession`/`requireSession`, e contém `resetMemberPasswordAction` (:180) e `generateResetLinkAction` (:116). `frontend/src/app/usuarios/actions.ts:204` (`resetarSenhaUsuarioAction`) idem. Recebem um `userId` arbitrário, executam `upsertUserPassword` + `DELETE auth.session` e **retornam a senha em texto** (ou o link de reset de 1h), falando direto no `authPool`/Better Auth. Não existe `middleware.ts` global. A irmã `uploadAvatarAction` (usuarios/actions.ts:235) **checa** a sessão — o guard existe no arquivo e foi omitido justo nas actions perigosas.
- **Impacto:** qualquer usuário logado (qualquer papel/empresa) reseta a senha de qualquer conta, inclusive superadmin. Os UUIDs vazam pelas telas de membros e por `GET /api/usuarios/exists/{id}` (M11).
- **Correção:** no início de cada action que toca `authPool`/Better Auth: `requireSession()` + checar `is_superadmin` OU `is_admin_of(empresa ativa)` + membership do alvo. Idealmente rotear pelo backend (que já tem `require_permission`).

### C2 — Painel Dokploy exposto na internet pública (porta 3000)
- **Domínio:** Infraestrutura · **Status:** ABERTO
- A porta 3000 responde do IP público `163.176.232.179` (docker-proxy em `0.0.0.0`; a Security List da OCI deixa passar). Acesso ao Dokploy = acesso a todos os envs e containers — inclui o `INTERNAL_SERVICE_TOKEN`.
- **Correção:** bloquear 3000 na Security List da OCI + regra no `DOCKER-USER`; acessar só via Tailscale (`100.116.235.14:3000`) ou pelo domínio com `ipAllowList` do Traefik para `100.64.0.0/10`; ativar 2FA no Dokploy. ~30 min, sem deploy.

---

## 🟠 Altos

### A1 — SSRF via URL de hook/menu/MCP (sem a guarda que só a mídia tem)
- **Domínio:** Injeção/SSRF · **Status:** ABERTO
- A guarda anti-SSRF forte (`_host_is_public` + revalidação de cada redirect) existe só no download de mídia. Os canais que fazem requisição de saída para URL configurada pela empresa **não** a usam: hooks (`shared/models.py:584` aceita `url` sem validar; POST em `shared/hook_dispatcher.py:82`), menu `chamar_webhook` (`worker/processor.py:2149`), MCP server (`server/routes/catalogo.py:393`).
- **Impacto:** admin cria hook para `http://169.254.169.254/…` (metadata) ou serviço interno; ao trocar mensagens, o backend faz o POST. Resposta 4xx/5xx → corpo (até 1000 chars) em `hook_dead_letter`, lido via `GET /api/hooks/dead-letter` → **oráculo de exfiltração**. Para 200, SSRF cego com oráculo de status/timing.
- **Correção:** extrair `_validate_media_url`/`_host_is_public` para um util anti-SSRF único e chamá-lo na criação e antes de cada requisição de saída controlada por tenant. Combina com M12.

### A2 — IDOR cross-tenant: invalidar sessões de qualquer usuário
- **Domínio:** Auth/RBAC · **Status:** ABERTO
- `POST /api/usuarios/{user_id}/sessions/invalidate` (`server/routes/usuarios.py:471`) exige só `require_permission("empresa.member.add")` e passa `user_id` direto para `invalidar_sessions` (`shared/usuarios.py:542`, `DELETE auth.session WHERE userId=$1` global, RLS bypass). Não valida que o alvo é da empresa do chamador.
- **Impacto:** force-logout repetido de usuário/superadmin de outro tenant (DoS de autenticação cross-tenant).
- **Correção:** validar `get_usuario(empresa_id, user_id) is not None` antes de invalidar.

### A3 — INTERNAL_SERVICE_TOKEN na query string dos docs de produção
- **Domínio:** Segredos / Web · **Status:** ABERTO
- `/docs` e `/redoc` aceitam `?token=<INTERNAL_SERVICE_TOKEN>` e **reinjetam** o token no HTML como `openapi_url=/openapi.json?token=…` (`server/main.py:288-297`). Esse token autentica qualquer chamada em `/api/*`. Query strings vão para o access log do Traefik, histórico e header `Referer`.
- **Correção:** aceitar o token só via header `Authorization`; nunca embutir na URL. (A comparação é timing-safe e devolve 404 — o problema é o canal.)

### A4 — is_admin_of lê role legado e ignora perfis
- **Domínio:** Auth/RBAC · **Status:** ABERTO (é a decisão arquitetural 2 já aprovada)
- `shared/empresa.py:632` concede acesso por `empresa_membro.role == 'admin'` cru, ignorando perfis. Endpoints com `require_permission` resolvem por perfil; os gateados por `is_admin_of` (editar empresa, logo/branding, CSAT, resumo, billing, workflow, calendar, atendimento) resolvem por role legado. Usuário rebaixado para perfil "Leitura" mas com `role='admin'` continua editando empresa/branding (vetor do XSS M5).
- **Correção:** `is_admin_of` deriva de `get_user_permissions`/perfil, com fallback no role só para quem não tem perfil. ~1–2h; maior risco da leva.

### A5 — SSH e serviços de host expostos sem firewall nem fail2ban; 187 updates
- **Domínio:** Infraestrutura · **Status:** ABERTO
- SSH 22 público (`PermitRootLogin without-password`, sem fail2ban). `firewalld` inativo, `INPUT ACCEPT`, `DOCKER-USER` vazio; `rpcbind` (111), `pmcd` (44321), `pmlogger` (4330) e Swarm (2377/7946) em `0.0.0.0`, filtrados só pela nuvem. 187 pacotes pendentes.
- **Correção:** restringir 22 ao tailnet; `PermitRootLogin no`; regras no `DOCKER-USER` (80/443 público, resto tailnet); desabilitar pcp/rpcbind; `dnf-automatic` security + reboot mensal.

### A6 — pypdf 5.1.0: DoS via PDF malicioso do cliente
- **Domínio:** Dependências · **Status:** ABERTO
- CVE-2026-57204 + 3 PYSEC. Cliente manda PDF pelo WhatsApp → worker extrai texto (`shared/file_extractor.py`) → loop infinito / DoS do worker serial (segura a fila de todas as empresas).
- **Correção:** pypdf 6.16+ e regenerar `uv.lock` (senão o build Docker quebra). Ver M13.

---

## 🟡 Médios

| ID | Domínio | Achado | Arquivo | Correção | Status |
|---|---|---|---|---|---|
| M1 | DoS/custo | Teto de IA não bloqueia: `ia_budget` default `alertar`; custo de transcrição/visão pago ANTES do gate; `plano.limite_orcamento_ia_usd` decorativo | processor.py:2468/2656/3029; governanca_ia.py:211 | gate antes de transcrição/visão; default `bloquear`; plugar limite de plano | ABERTO |
| M2 | DoS | Rate limit por telefone roda DEPOIS do download de mídia; download sem teto de bytes | evolution_webhook.py:295–389; midia_processing.py:150 | rate limit antes; cap de `Content-Length`/bytes nos 3 caminhos | ABERTO |
| M3 | DoS | SSE abre 1 conexão PG (DSN superuser, fora do pool) por stream, sem cap → esgota `max_connections=100` | atendimento.py:477; hitl.py:195; push_loop | semáforo por operador; pool separado. É o gargalo de capacidade dos 10 clientes | ABERTO |
| M4 | Web | Nenhuma CSP — API nem Next | middlewares.py:37; next.config.ts | CSP restritiva (nonce por causa do `<style>` de branding e next-themes) | ABERTO |
| M5 | Web | XSS stored: cor de marca em `<style>` via `dangerouslySetInnerHTML` sem escape no front; gate único é o regex da API | layout.tsx:181,77–101; empresa_admin.py:88 | validar `^#[0-9a-f]{6}$` também no front | ABERTO |
| M6 | Upload | Stored XSS: mídia servida inline com Content-Type do remetente, sem `Content-Disposition` | atendimento.py:783; shared/atendimento.py:1073 | `Content-Disposition: attachment` + allowlist de mime | ABERTO |
| M7 | Auth/RBAC | RLS permissivo quando falta `X-Empresa-Id`; contexto vem do header cru, não do valor validado | middlewares.py:200; db.py:110 | `get_empresa_context` re-seta o contexto validado; avaliar default-deny | ABERTO |
| M8 | Segredos | Chave que cifra as credenciais dos clientes derivada do `INTERNAL_SERVICE_TOKEN` (sem separação de chaves; SHA-256 1 rodada) | integrations/crypto.py:23; config.py:156 | exigir `INTEGRACOES_ENCRYPTION_KEY` dedicada em prod | ABERTO |
| M9 | Segredos/DoS | Validação de apikey do webhook Evolution off por default; só exigida em `OUTBOUND_MODE=real` → em modo mock aceita webhook forjado | evolution_webhook.py:167; config.py:359,362,468 | exigir apikey independente do outbound_mode | ABERTO |
| M10 | Upload | `file.read()` carrega o corpo inteiro em RAM antes do check; `responder-midia` sem cap | atendimento.py:1044; usuarios.py:501; empresa_admin.py:312 | streaming com corte no cap; limite no Traefik | ABERTO |
| M11 | Auth/RBAC | `GET /api/usuarios/exists/{id}` sem escopo → id/nome/email de qualquer user global | usuarios.py:455; shared/usuarios.py:523 | escopar por membership da empresa ativa | ABERTO |
| M12 | Auth/RBAC | Hooks sem `require_permission` — qualquer membro cria webhook e exfiltra mensagens do tenant (e habilita A1) | routes/hook.py:54–109 | gate de permissão/role na criação | ABERTO |
| M13 | Dependências | `python-multipart` 0.0.22 (5 CVEs), `starlette` 0.52.1 (6 PYSEC), `urllib3` 2.6.3 / `requests` 2.32.5, `setuptools`, `python-dotenv` | uv.lock | upgrade + regen `uv.lock`; starlette é upgrade maior (testar) | ABERTO |

---

## ⚪ Baixos / informativos

| Domínio | Achado | Nota |
|---|---|---|
| Upload | Pillow decompression bomb só barra em 2×MAX_IMAGE_PIXELS (~178M px) | setar `MAX_IMAGE_PIXELS` ~40M nos 3 handlers |
| Web/Upload | `/uploads/*` sem auth; logo `{empresa_id}.png` sequencial → branding enumerável | sensibilidade baixa; nomes não-sequenciais ou auth no proxy |
| Upload | Credencial default do MinIO se o env não for setado | mitigado: MinIO sem `ports:`, bucket privado |
| Upload | XLSX/openpyxl zip-bomb (sharedStrings antes do cap de linhas) | cap de 10 MB limita; XXE não explorável (parser stdlib) |
| Segredos | Sem anti-replay nos webhooks | mitigado por idempotência `ON CONFLICT DO NOTHING` por message_id |
| Auth/Segredos | Token/link de reset em texto puro em `auth.password_reset_pending` (1h) | decisão de design (mig 025); secundário a C1 |
| Web/Auth | cookie `active_empresa_id` sem `secure`/`httpOnly` | revalidado no servidor (403 se não-membro); adicionar `secure` |
| Injeção | DNS rebinding / TOCTOU na guarda anti-SSRF da mídia (resolve DNS 2×) | exige media_url atacante-controlada + rebinding; pin de IP |
| Injeção | Prompt injection stored via `pushName` em `{{cliente.nome}}` no system prompt | escopo do tenant; sem exfil cross-empresa; sem SSTI. Escapar dados do cliente no ctx |
| Injeção | Download de mídia WABA sem a guarda anti-SSRF | URL vem da Graph API da Meta (lookaside), não do atacante — baixo |
| Arquitetura | Confiança em `X-User-Id`/`X-Empresa-Id` num único segredo estático (`INTERNAL_SERVICE_TOKEN`) | timing-safe + ≥32 chars presentes; ponto único de comprometimento — reforça C2/A3/M8 |

---

## Defesas verificadas como corretas (não retrabalhar)

- **SQL injection fechado** — parametrização pyformat consistente; `ORDER BY` dinâmico por allowlist; builders `f"{col} = %s"` recebem chaves de modelos Pydantic (extras ignorados), não input cru.
- **Assinaturas timing-safe** em todos os caminhos — service token, HMAC WABA (fail-closed: rejeita sem secret/assinatura), apikey Evolution, token Asaas, verify_token WABA, api_key da empresa.
- **SSRF do download de mídia bem defendido** — `_host_is_public` bloqueia loopback/privado/link-local (169.254 metadata)/reserved, IPv6, octal/decimal, e revalida cada redirect. (A lacuna é não replicar nos outros canais — A1.)
- **Object storage sem furo** — presigned URL definida mas nunca usada (mídia vira `data:` URL em memória, anti-SSRF); object key = `uuid4`; IDOR de mídia fechado por `WHERE id AND atendimento_id AND empresa_id`; MinIO não exposto.
- **Uploads de imagem re-encodados por Pillow** (descarta SVG/HTML/polyglot); path traversal barrado (sanitização + StaticFiles).
- **Sem command injection** — `antiword` via `create_subprocess_exec` (sem shell), tempfile aleatório; nenhum `eval`/`shell=True`/`pickle.loads`.
- **Auth** — bearer móvel valida contra `auth.session` no banco e tem precedência sobre `X-User-Id`; rotas de plataforma com `_exigir_superadmin`; CORS por lista explícita; rate limits de login nos caminhos certos; link de reset e chave OpenRouter não aparecem em log; `.env` não rastreado.
- **Fila** — poison pill vai para `failed` após 3 tentativas; export CSV/XLSX com `EXPORT_ROW_CAP`; `/webhook/sync` só fora de produção.
- **Backups GPG** — `--passphrase-file` (não vaza em `ps`), AES256, arquivo 600; `pg_dump` sem senha em env/linha de comando.

---

## Plano de remediação (ordem)

1. **Hoje — C1 e C2.** `requireSession` + admin/superadmin + membership nas três Server Actions de reset; fechar 3000 e SSH público (Security List OCI + `DOCKER-USER`), 2FA no Dokploy.
2. **Semana — Altos.** Util anti-SSRF único em hooks/menu/MCP (A1) + permissão nos hooks (M12); escopo de empresa em `sessions/invalidate` (A2) e `exists` (M11); token fora da query (A3); upgrade pypdf + regen `uv.lock` (A6); endurecimento do host (A5).
3. **Decisão 2 (A4)** — `is_admin_of` por perfil.
4. **Custo e capacidade (M1–M3)** — casam com a expansão de clientes.
5. **Endurecimento web (M4–M6)** — CSP; cor no front; `Content-Disposition`.
6. **Resto (M7–M13 + baixos).**
7. **Cadência** — `pip-audit` no CI; revisar Server Actions novas (guard explícito, não herdado); repetir o red team a cada leva grande.

Ver também: `docs/AUTH.md`, `docs/RLS_OPERATIONS.md`, `docs/DOKPLOY.md`, `docs/BACKUP.md`, `docs/CUSTO_E_CAPACIDADE.md`.
