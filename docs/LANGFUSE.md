# Langfuse — Observabilidade LLM self-hosted

Integração Langfuse v3 self-hosted via Docker. Adiciona ao stack:

- **Trace por turno** com `prompt_version`, `latency_ms`, `input_tokens` /
  `output_tokens`, `tool_calls[]`, modelo, custo.
- **Prompt Management** — `SYSTEM_PROMPT` do agente vive no Langfuse, hot-swap
  por label (`production` / `latest`) sem deploy. Fallback Python embutido.
- **User feedback (NPS)** — quando o cliente responde o CSAT do atendimento
  (`atendimento_avaliacao`), a nota 0-10 vira `score` anexado à trace do turno.

Feature **opt-in**: sem `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` no `.env`,
todo o código é no-op silencioso. O worker nunca falha por Langfuse offline.

---

## 1. Subir a stack

```bash
make langfuse-up           # sobe web + worker + clickhouse + redis + minio + db
make langfuse-logs         # tail
make langfuse-down         # derruba (mantém volumes)
make langfuse-reset        # DROP volumes (perde traces e projetos)
```

A 1ª subida demora ~60s (migrations ClickHouse + bootstrap web). Health check:

```bash
curl -fsS http://localhost:3001/api/public/health
```

**RAM**: ClickHouse + Postgres dedicado + Minio + Redis pesam ~1.5GB. Por isso
a stack vive em `docker-compose.langfuse.yml` separado e não sobe junto com
`make up`. A network `langfuse_net` é isolada do compose principal.

**Porta**: `langfuse-web` é exposto em **3001** (não 3000) pra evitar
conflito com o frontend Next.js do projeto.

---

## 2. Criar projeto + copiar API keys

1. Acessar <http://localhost:3001>
2. Criar organização (ex: `nexus`) → projeto (ex: `whatsapp-langchain-dev`)
3. Settings → API Keys → **Create new API keys**
4. Copiar para o `.env` da aplicação principal:

   ```bash
   LANGFUSE_HOST=http://localhost:3001
   LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
   LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
   LANGFUSE_ENVIRONMENT=development
   LANGFUSE_PROMPT_LABEL=latest      # "latest" em dev, "production" em prod
   ```

5. Reiniciar API + Worker (`make down && make up`). Logs do worker devem mostrar
   `langfuse_client_initialized`.

---

## 3. O que é capturado automaticamente

Toda mensagem entrante → 1 turno do agente → 1 trace no Langfuse contendo:

| Captura            | Origem                                            |
| ------------------ | ------------------------------------------------- |
| `trace_id`         | determinístico: `Langfuse.create_trace_id(seed="msg:<id>")` |
| `user_id`          | `phone_number` do cliente                         |
| `session_id`       | `thread_id` (`phone:agent`) — agrupa conversa     |
| `input` / `output` | mensagem do cliente / resposta do agente          |
| `model`            | resolvido em `shared/llm.py` (OpenRouter)         |
| `prompt_version`   | versão do prompt resolvida via Prompt Management  |
| `latency_ms`       | tempo total do `graph.ainvoke`                    |
| `tokens` (in/out)  | `usage_metadata` propagada pelo LangChain         |
| `tool_calls[]`     | qualquer tool acionada (calendar, RAG, memory…)   |
| metadata           | `empresa_id`, `atendimento_id`, `agent_id`        |

A integração usa `langfuse.langchain.CallbackHandler` plugado em
`invoke_config["callbacks"]` no worker. O outro callback (`IaExecucaoCallback`,
que grava `ia_execucao`) continua ativo em paralelo — eles cobrem fontes
distintas (DB local pra dashboards internos, Langfuse pra debug visual).

---

## 4. Prompt Management

### 4.1 Subir prompt do código pra o Langfuse

No painel, **Prompts → New prompt**. Convenção de nome do projeto:

```text
system-prompt:<template_id>
```

Onde `template_id` é o slug do agente (`atendimento_router`,
`atendimento_completo`, `agendamentos`, `vsa_tech`). Cole o conteúdo de
`src/whatsapp_langchain/agents/catalog/<id>/prompts.py::SYSTEM_PROMPT`.

Marque a label apropriada (`latest` em dev, `production` em prod).

### 4.2 Como o loader resolve

`agents/loader.py` chama `langfuse_client.get_system_prompt(name, fallback)`:

1. Se Langfuse off → retorna fallback (constante Python).
2. Se Langfuse on + prompt existe → retorna texto + metadata `{prompt_name,
   prompt_version}` que vai pro trace.
3. Se Langfuse on + prompt **não** existe → retorna fallback (silencioso).

O resolved text passa pelo `render_template` do projeto (`{{empresa.*}}`,
`{{data.*}}`, etc) antes de virar instrução do agente. **Não use a sintaxe
mustache de variáveis `{{var}}` do Langfuse aqui** — o render é nosso, não
do SDK.

### 4.3 Mudar prompt em produção sem deploy

1. Painel → Prompts → editar SYSTEM_PROMPT → **Save as new version**
2. Promover a label `production` na nova versão
3. Cache do worker é 60s (definido em `langfuse_client.get_system_prompt`)
4. Próxima mensagem usa novo texto. Trace mostra `prompt_version: <n>` novo.

---

## 5. NPS → Score

Fluxo automático sem configuração adicional:

1. Operador fecha atendimento (ou cliente digita "encerrar atendimento").
2. Worker dispara mensagem CSAT (config `empresa.csat_*`, mig 074).
3. Cliente responde nota 0-10 → `save_avaliacao(atendimento_id, nota=X)`.
4. `_post_nps_to_langfuse` busca `langfuse_trace_id` do último `ia_execucao`
   daquele atendimento e chama `langfuse.create_score(name="nps", value=nota,
   trace_id=...)`.
5. Se cliente envia comentário em até 60s, segundo score `nps_comment` é
   anexado ao mesmo trace.

No painel: trace ganha badges `nps=9` + `nps_comment="Atendimento rápido"`.
Filtrar por score no dashboard pra achar conversas detratoras.

---

## 6. Produção (Dokploy)

Stack roda como **segundo Compose service** no projeto `vsanexus` no Dokploy
(separado do `chat.vsanexus.com`).

### 6.1 Criar o Compose service no Dokploy

1. **Projects → vsanexus → Create Service → Compose**
2. **Source**: GitHub branch (mesmo repo `whatsapp-langchain`)
3. **Compose Path**: `docker-compose.langfuse.yml`
4. Salvar — **não fazer Deploy ainda**.

### 6.2 Setar variáveis de ambiente (UI Dokploy)

No service → **Environment** → adicionar:

```bash
# Gerar uma vez (UM por var; NÃO reusar a mesma string):
#   openssl rand -hex 32
LANGFUSE_SALT=<64 hex chars>
LANGFUSE_ENCRYPTION_KEY=<64 hex chars>     # OBRIGATÓRIO 64 hex
LANGFUSE_NEXTAUTH_SECRET=<32+ chars>

# URL pública — bate com o domínio configurado no passo 6.3
LANGFUSE_PUBLIC_URL=https://langfuse.vsanexus.com
```

Os defaults do compose (`langfuse_dev_*`) servem só pra `make langfuse-up`
local. Em prod o startup do `langfuse-web` aborta se `ENCRYPTION_KEY` é o
default zerado.

### 6.3 Expor `langfuse-web` no domínio

Service → **Domains → Create Domain**:

| Campo | Valor |
| ----- | ----- |
| Host  | `langfuse.vsanexus.com` |
| Path  | `/` (atenção bug `addPrefix` quando path != "/", vide `docs/DOKPLOY.md`) |
| Service Name | `langfuse-web` |
| Container Port | `3000` (porta interna do Node — NÃO 3001) |
| HTTPS | ✅ on (Let's Encrypt) |

Apontar registro DNS `langfuse.vsanexus.com` → IP do host Dokploy antes
do Deploy (senão Let's Encrypt falha no challenge).

### 6.4 Deploy

Service → **Deploy**. Aguardar 5 serviços virarem healthy (~2-3min). Logs:
**Deployments → Live Logs → langfuse-web** — esperar `Ready in N ms`.

### 6.5 Bootstrap do painel + keys

1. Abrir https://langfuse.vsanexus.com → criar conta (1ª vira admin).
2. Criar organização `nexus-chat` + projeto `whatsapp-langchain-prod`.
3. **Project Settings → API Keys → Create new** → copiar keys.

### 6.6 Conectar aplicação principal

No service do `chat.vsanexus.com` (Compose principal), adicionar env vars:

```bash
LANGFUSE_HOST=https://langfuse.vsanexus.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_ENVIRONMENT=production
LANGFUSE_PROMPT_LABEL=production
```

**Redeploy** do service principal pra carregar as keys. Logs do worker
devem mostrar `langfuse_client_initialized host=https://langfuse.vsanexus.com`.

### 6.7 Subir prompts + smoke E2E

1. Painel Langfuse → Prompts → criar `system-prompt:<template_id>` pra
   cada agente do catálogo, label `production`.
2. Mandar mensagem real em `chat.vsanexus.com` (WhatsApp produção).
3. Painel → Traces → confirmar trace com `environment=production`,
   `model`, `tokens`, `tool_calls`, `prompt_version`.
4. Fechar atendimento → cliente responde CSAT 0-10 → trace ganha `score
   nps=N`.

### 6.8 Caveats Dokploy

- **Volumes**: Dokploy cria volumes named (`langfuse_postgres_data` etc.)
  no host. Backup via snapshot do disco ou `docker run --rm -v
  langfuse_postgres_data:/data alpine tar czf - /data`.
- **Memória**: stack pesa ~1.5GB (ClickHouse é o maior). Se o host
  estiver perto do limite, considere subir só LANGFUSE em outro host
  Dokploy menor.
- **Bug `addPrefix`**: ao configurar Domains, manter path `/` (não usar
  `/langfuse` ou similar) — Traefik do Dokploy tem bug que injeta
  redirects errados quando path != "/". Vide [[reference_dokploy]].
- **Não mapear porta no host**: o `ports: 3001:3000` do compose é só
  pra dev local. Em Dokploy o roteamento é via Traefik na rede interna
  do projeto — você pode remover essa linha em prod ou deixar (Dokploy
  ignora porta de host quando você usa Domain).

---

## 7. Langfuse × LangSmith

A integração do `docs/LANGSMITH.md` (datasets + LLM-as-judge) continua
funcionando em paralelo — Langfuse e LangSmith não conflitam. Usos típicos:

| Necessidade                              | Use         |
| ---------------------------------------- | ----------- |
| Ver tokens/latência/tools de um turno    | **Langfuse**  |
| Hot-swap de SYSTEM_PROMPT sem deploy     | **Langfuse**  |
| Anexar NPS como score à trace            | **Langfuse**  |
| Self-hosted, dado fica em casa           | **Langfuse**  |
| Datasets curados pra eval offline        | **LangSmith** |
| LLM-as-judge sob curva LangChain         | **LangSmith** |

Você pode habilitar os dois ao mesmo tempo — cada `invoke_config["callbacks"]`
aceita N callbacks. Hoje o worker injeta só Langfuse + `IaExecucaoCallback`,
mas o caminho pra plugar LangSmith é o mesmo (`LANGSMITH_TRACING=true` já
ativa via env no LangChain core).

---

## 8. Troubleshooting

### `langfuse_client_init_failed` no log do worker

- `LANGFUSE_HOST` deve incluir scheme (`http://` ou `https://`)
- Container do worker enxerga `localhost:3001`? Se o worker rodar fora do
  compose Langfuse (rede própria), use `http://host.docker.internal:3001`
  no Linux só funciona via flag `--add-host=host.docker.internal:host-gateway`.
- Verifique credenciais com `curl -u pk-lf-...:sk-lf-... http://localhost:3001/api/public/health`

### Traces não aparecem

- Worker está com keys? `docker logs whatsapp-langchain-worker | grep langfuse`
- Cliente flush é assíncrono (default 5s). Mande 3 mensagens consecutivas
  pra forçar flush por batch size.

### Prompt do painel não foi aplicado

- Conferir `LANGFUSE_PROMPT_LABEL`: deve bater com a label promovida no painel.
- Cache TTL é 60s. Restart do worker derruba cache imediatamente.

### Tabelas `langfuse_*` no Postgres principal

Não existem — Langfuse usa Postgres **dedicado** (container `langfuse-db`)
mais ClickHouse pra spans. Nosso DB (`whatsapp_langchain`) só ganhou colunas
`langfuse_trace_id` nas tabelas `ia_execucao` e `message_queue` (mig 107).
