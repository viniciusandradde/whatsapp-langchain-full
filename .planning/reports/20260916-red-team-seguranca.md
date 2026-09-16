# Red team de segurança — Chat Nexus (2026-09-16)

Avaliação autorizada pelo dono sobre o código de produção. 6 agentes em paralelo (auth/RBAC, injeção/SSRF, web/frontend, segredos/cripto, upload/storage, DoS/custo) + recon de infraestrutura + pip-audit. Achados alto+ reverificados no código. Artefato: "Red Team Chat Nexus". **Nada corrigido — só diagnóstico.**

Contagem: 2 críticos, 6 altos, 13 médios, 11 baixos/info, 30+ defesas corretas.

## CRÍTICOS
- **C1 — Server Actions de reset de senha SEM authz → takeover cross-tenant.** `frontend/src/app/companies/[id]/members/actions.ts` tem 0 `getSession`/`requireSession` (contém `resetMemberPasswordAction:180`, `generateResetLinkAction:116`); `usuarios/actions.ts:204` `resetarSenhaUsuarioAction` idem. Recebem `userId` arbitrário, `upsertUserPassword`+`DELETE auth.session`, retornam senha em texto/link 1h, direto no authPool. Sem `middleware.ts` global (confirmado). Irmã `uploadAvatarAction:235` checa sessão. Qualquer logado (qualquer role/empresa) reseta admin/superadmin. VERIFICADO. Fix: requireSession + is_superadmin/is_admin_of + membership do alvo em cada action.
- **C2 — Dokploy :3000 público** (recon externo 16/09). Ver [[checkpoint_capacidade_10_clientes]]. Fix: Security List OCI + DOCKER-USER + 2FA.

## ALTOS
- **A1 — SSRF via hook/menu/MCP.** Guarda anti-SSRF (`_host_is_public`) só existe no download de mídia; hooks (`hook_dispatcher.py:82`, url de `models.py:584` sem validar), menu `chamar_webhook` (`processor.py:2149`) e MCP (`catalogo.py:393`) fazem requisição de saída para URL do tenant SEM validar. Hook 4xx/5xx → corpo (1000 chars) em `hook_dead_letter`, lido via API = oráculo de exfil. VERIFICADO (hook_dispatcher.py:82). Fix: util anti-SSRF único na criação e no uso.
- **A2 — IDOR invalidar sessão cross-tenant.** `POST /api/usuarios/{user_id}/sessions/invalidate` (usuarios.py:471) só `require_permission("empresa.member.add")`, sem escopo; `invalidar_sessions` bypassa RLS, DELETE global. Force-logout de user de outro tenant. VERIFICADO. Fix: validar membership antes.
- **A3 — INTERNAL_SERVICE_TOKEN na query string dos docs.** `main.py:288-297` reinjeta `?token=` no HTML; token vaza em log do Traefik/Referer/histórico e autentica todo `/api/*`. VERIFICADO. Fix: só header.
- **A4 — is_admin_of lê role legado, ignora perfis** (`empresa.py:632`). É a decisão 2 pendente. Escalonamento: role admin com perfil Leitura ainda edita empresa/branding (vetor do XSS M5). Ver [[decisoes_arquiteturais_2026-09-16]].
- **A5 — SSH público sem fail2ban + firewall inexistente + 187 updates** (recon). PermitRootLogin without-password, firewalld off, DOCKER-USER vazio, rpcbind/pmcd/swarm em 0.0.0.0.
- **A6 — pypdf 5.1.0 DoS** (CVE-2026-57204 + 3 PYSEC). Cliente manda PDF → worker extrai → loop infinito, trava a fila serial. pip-audit. Fix: pypdf 6.16+ + regen uv.lock.

## MÉDIOS (resumo)
M1 teto de IA não bloqueia (default alertar; custo de transcrição/visão antes do gate; plano.limite decorativo) · M2 rate limit depois do download de mídia + sem cap de bytes · M3 SSE 1 conexão PG superuser/stream sem cap (=gargalo de capacidade) · M4 sem CSP · M5 XSS stored branding (cor em <style>, gate único regex API) · M6 XSS stored mídia inline com Content-Type do remetente sem Content-Disposition · M7 RLS permissivo sem X-Empresa-Id (backstop desarmado) · M8 chave de cifra das credenciais derivada do service token · M9 apikey Evolution off por default (modo mock aceita webhook forjado) · M10 file.read() sem limite antes do check (responder-midia sem cap) · M11 GET exists/{id} sem escopo (PII cross-tenant) · M12 hooks sem require_permission (membro exfiltra msgs + habilita A1) · M13 deps python-multipart/starlette/urllib3/requests.

## BAIXOS/INFO
Pillow bomb (2×MAX) · /uploads/* sem auth, logo {empresa_id}.png enumerável · MinIO cred default (mitigado: sem ports) · XLSX zip-bomb · sem anti-replay webhook (mitigado por idempotência) · reset token em claro no DB (design) · cookie active_empresa_id sem secure · DNS rebinding TOCTOU na mídia · prompt injection stored via pushName em {{cliente.nome}} · WABA media download sem guarda · confiança em X-User-Id/X-Empresa-Id apoiada num único segredo estático.

## DEFESAS CORRETAS (não mexer)
SQLi fechado (pyformat + allowlist ORDER BY + chaves Pydantic); assinaturas timing-safe fail-closed (HMAC WABA, apikeys); SSRF de mídia bem defendido (host público + redirect); object storage sem furo (presigned nunca usada, key uuid4, IDOR fechado, MinIO não exposto); imagens re-encodadas por Pillow; sem command injection; bearer móvel valida no banco; plataforma com _exigir_superadmin; CORS lista explícita; backups GPG --passphrase-file AES256.

## Plano
1. Hoje: C1 (authz nas actions de reset) + C2 (porta 3000/SSH).
2. Semana: A1 (util anti-SSRF + M12) · A2/M11 (escopo) · A3 (token) · A6 (pypdf) · A5 (host).
3. Decisão 2 (A4).
4. Custo/capacidade M1–M3 (casa com 10 clientes).
5. Web M4–M6.
6. Resto médios/baixos.
7. Cadência: pip-audit no CI, revisar Server Actions novas, repetir red team por leva.

Escopo não coberto (dinâmico): pentest ativo na instância viva, fuzzing, workflows LangGraph em prod.
