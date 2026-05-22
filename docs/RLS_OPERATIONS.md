# RLS Operations Runbook — Chat Nexus

**Sprint A.2 SHIPPED 2026-05-22** · Postgres 16.14 · Maturidade RLS 10/10

Este runbook cobre operação e troubleshooting do Row-Level Security em produção.

---

## Arquitetura de roles

| Role | Permissões | Uso | Conexão |
|---|---|---|---|
| `postgres` | SUPERUSER + BYPASSRLS | Migrations, backups, debug admin | `CONNECTION LIMIT 10` |
| `chat_nexus_app` | NOSUPERUSER, NOBYPASSRLS, CRUD | **API + Worker runtime** | `CONNECTION LIMIT 50` |
| `chat_nexus_migrator` | NOSUPERUSER, NOBYPASSRLS, CREATEDB, ALL PRIV | Aplicar migrations | `CONNECTION LIMIT 3` |
| `chat_nexus_readonly` | NOSUPERUSER, NOBYPASSRLS, SELECT | BI / Grafana / Metabase | `CONNECTION LIMIT 20` |
| `chat_nexus_audit` | NOSUPERUSER, **BYPASSRLS**, SELECT | Compliance LGPD cross-tenant | `CONNECTION LIMIT 5` |

**Verificar status**:
```sql
SELECT * FROM app_roles_status;
SELECT * FROM security_hardening_status;
SELECT * FROM rls_status;
```

---

## Política RLS

Função `_rls_tenant_match(empresa_id)` decide acesso por row:

1. Se `app.bypass_rls = 'true'` → **TRUE** (superadmin / webhook lookup / health ops)
2. Se `app.empresa_id` vazio → **FALSE** (STRICT — Sprint A.2.3)
3. Se setado → `row.empresa_id = app.empresa_id`

58 tabelas com RLS+FORCE. Política aplicada via `tenant_isolation` em cada uma.

---

## Como o app seta o context

### API (request HTTP)
Middleware `install_rls_context` em `server/middlewares.py`:
1. Extrai header `X-Empresa-Id` (Better Auth envia)
2. Seta `contextvars.ContextVar` (per-task)
3. Wrapper `_RlsAwarePool.connection()` em `shared/db.py` executa `SET app.empresa_id` em cada conn entregue

### Worker (processamento de mensagem)
`worker/main.py` envolve cada msg em `with empresa_scope(message.empresa_id)`. Same contextvar.

### Pontos com bypass explícito (cross-tenant legítimo)
- `claim_next_message` (worker/consumer.py) — claim cross-empresa da fila
- `list_active_calendar_empresas` (shared/agendamento.py) — cron lista empresas
- `cleanup_zumbis_all_empresas` (shared/atendimento_cleanup.py)
- `get_conexao_by_from_number / evolution_instance / waba_phone_id` (shared/conexao.py) — webhook descobre empresa
- `health_queue / health_agent / health_workers` (server/routes/health.py)

Audit: `grep -rn "bypass=True\|bypass_rls" src/` deve listar TODOS os pontos.

---

## Runbook: rotação de senha

A cada 90 dias (ou após incidente):

```bash
# 1) Gerar nova senha
NEW_PASS=$(openssl rand -base64 36 | tr -d '/+=' | head -c 32)
echo "Nova senha: $NEW_PASS"   # SALVAR no vault AGORA

# 2) Alterar no DB (rodar como postgres)
sg docker -c "docker exec -i projetos-chatvsanexus-er02mp-db-1 psql -U postgres whatsapp_langchain" <<SQL
ALTER ROLE chat_nexus_app WITH PASSWORD '$NEW_PASS';
SQL

# 3) Atualizar Dokploy env var DATABASE_URL_APP
#    → painel Compose → Environment → editar → save → redeploy
#    Sessões existentes mantêm conexão; reconexões usam senha nova.

# 4) Validar
curl https://api.vsanexus.com/health   # 200 esperado
curl https://api.vsanexus.com/api/queue   # 401 (auth ok)
```

---

## Runbook: emergency bypass

Cenário: app travou porque RLS bloqueando algo inesperado.

**Opção 1 (preferida) — restaurar role temporariamente**:
```sql
ALTER ROLE chat_nexus_app BYPASSRLS;
-- ... investigar / corrigir ...
ALTER ROLE chat_nexus_app NOBYPASSRLS;
```

**Opção 2 — rollback DATABASE_URL pro postgres**:
- Dokploy env → deletar `DATABASE_URL_APP` → save → redeploy
- App volta pra modo legacy (sem RLS efetivo)
- Reaplicar quando bug corrigido

**Opção 3 — rollback policy pra permissive**:
```sql
-- Reaplica mig 096 (versão permissive)
sg docker -c "docker cp db/migrations/096_rls_enable.sql projetos-chatvsanexus-er02mp-db-1:/tmp/096.sql && docker exec projetos-chatvsanexus-er02mp-db-1 psql -U postgres whatsapp_langchain -f /tmp/096.sql"
```

---

## Runbook: incident response — suspeita de vazamento cross-tenant

1. **Identificar** request_id ou pattern no log do incidente
2. **Audit query**:
   ```sql
   -- DDL recente (qq mudança de role/policy)
   SELECT * FROM _ddl_role_audit
    WHERE occurred_at > '2026-05-22 00:00'
    ORDER BY occurred_at DESC;

   -- Quem está conectado como postgres (superuser)
   SELECT pid, usename, application_name, client_addr, query_start, query
     FROM pg_stat_activity
    WHERE usename = 'postgres' AND state = 'active';
   ```
3. **Forensics LGPD**:
   ```sql
   SELECT * FROM lgpd_event_log
    WHERE empresa_id = <vítima>
      AND created_at > '<timestamp>'
    ORDER BY created_at;
   ```
4. **Containment**: revogar role app comprometido:
   ```sql
   ALTER ROLE chat_nexus_app CONNECTION LIMIT 0;
   -- Forçar disconnect de sessões ativas:
   SELECT pg_terminate_backend(pid)
     FROM pg_stat_activity
    WHERE usename = 'chat_nexus_app';
   ```
5. **Notificar** DPO + ANPD (Art. 48 LGPD — 24-72h se PII vazado)

---

## Runbook: validar RLS continua funcionando

Smoke test executável a qualquer hora (não-destrutivo):

```bash
source /home/opc/.config/chat_nexus/app_roles_passwords.env

# 1) chat_nexus_app sem context = 0 rows (STRICT)
sg docker -c "docker exec projetos-chatvsanexus-er02mp-db-1 env PGPASSWORD='$CHAT_NEXUS_APP_PASSWORD' psql -U chat_nexus_app -d whatsapp_langchain -h localhost -tAc 'SELECT count(*) FROM cliente;'"
# Esperado: 0

# 2) chat_nexus_app com context = N rows
sg docker -c "docker exec projetos-chatvsanexus-er02mp-db-1 env PGPASSWORD='$CHAT_NEXUS_APP_PASSWORD' psql -U chat_nexus_app -d whatsapp_langchain -h localhost -tAc \"BEGIN; SELECT set_config('app.empresa_id','1',true); SELECT count(*) FROM cliente; COMMIT;\""
# Esperado: N (clientes da empresa 1)

# 3) chat_nexus_app context=999 = 0 (empresa que não existe / sem dados)
sg docker -c "docker exec projetos-chatvsanexus-er02mp-db-1 env PGPASSWORD='$CHAT_NEXUS_APP_PASSWORD' psql -U chat_nexus_app -d whatsapp_langchain -h localhost -tAc \"BEGIN; SELECT set_config('app.empresa_id','999',true); SELECT count(*) FROM cliente; COMMIT;\""
# Esperado: 0 (RLS filtra)

# 4) chat_nexus_audit cross-tenant = sempre todos
sg docker -c "docker exec projetos-chatvsanexus-er02mp-db-1 env PGPASSWORD='$CHAT_NEXUS_AUDIT_PASSWORD' psql -U chat_nexus_audit -d whatsapp_langchain -h localhost -tAc 'SELECT count(*) FROM cliente;'"
# Esperado: total real (BYPASSRLS funcionando)
```

E suite de testes E2E:

```bash
TOKEN=$(cat ~/.config/dokploy/token)
PG_PASS=$(curl -sS -H "x-api-key: $TOKEN" "https://dockploy.vsatecnologia.com.br/api/compose.one?composeId=yP8q8tXHmGGiKhusSK-h8" | python3 -c "import json,sys;[print(l.split('=',1)[1].strip()) for l in json.load(sys.stdin)['env'].split('\n') if l.strip().startswith('POSTGRES_PASSWORD=')]")
source /home/opc/.config/chat_nexus/app_roles_passwords.env
DB_HOST=192.168.144.2
DATABASE_URL="postgresql://postgres:$PG_PASS@$DB_HOST:5432/whatsapp_langchain" \
DATABASE_URL_APP_TEST="postgresql://chat_nexus_app:$CHAT_NEXUS_APP_PASSWORD@$DB_HOST:5432/whatsapp_langchain" \
uv run pytest tests/integration/test_rls_isolation.py -v -m docker_demo
# Esperado: 10 passed
```

---

## Audit dashboard

```sql
-- Estado geral
SELECT * FROM security_hardening_status;

-- Mudanças DDL recentes (login attempts, GRANTs etc)
SELECT occurred_at, session_user_at, command_tag, object_identity
  FROM _ddl_role_audit
 WHERE occurred_at > NOW() - INTERVAL '24 hours'
 ORDER BY occurred_at DESC;

-- Conexões ativas por role
SELECT usename, count(*), array_agg(DISTINCT application_name)
  FROM pg_stat_activity
 GROUP BY usename;

-- Tabelas com RLS
SELECT * FROM rls_status ORDER BY tabela;

-- PII opt-in por empresa
SELECT * FROM cliente_pii_audit;

-- ACL agente
SELECT * FROM agente_acl_status;
```

---

## Limitações conhecidas

- **pgaudit não instalado** — imagem `postgres:16` oficial Dokploy não inclui. TODO: trocar pra build custom em sprint futura.
- **`postgres` ainda é necessário** pro migrator pool (CREATE EXTENSION pgvector, etc). `CONNECTION LIMIT 10` mitiga, mas senha ainda existe em env.
- **49 tabelas tenant via FK indireto** (sem coluna `empresa_id`): `cliente_anotacao`, `cliente_tag`, `atendimento_menu_historico`, etc — NÃO têm RLS direta. Mitigado por FK CASCADE (empresa deletada → filhos deletados) + queries sempre fazem JOIN. TODO: denormalizar `empresa_id` ou criar policy via JOIN.
- **Memory store LangGraph** (`store`, `store_vectors`, `checkpoints*`) — gerenciado pelo próprio LangGraph, sem RLS. Tenant isolation via `thread_id` + `user_id` que incluem phone único.
