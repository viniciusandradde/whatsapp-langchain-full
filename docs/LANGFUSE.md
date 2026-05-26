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

A 1ª subida demora ~60s (migrations ClickHouse + bootstrap web). Health check
(dentro da rede do compose):

```bash
docker compose -f docker-compose.langfuse.yml exec langfuse-web \
  wget -qO- http://$HOSTNAME:3000/api/public/health
```

**Acesso pelo navegador em DEV local**: o compose **não publica porta** no
host (escolha de design pra não conflitar com outros projetos no host
Dokploy). Opções:

1. **Acessar via Traefik local** (se já tem Dokploy/Traefik rodando local):
   adicionar Domain `langfuse.localhost`.
2. **Bind ad-hoc**: `docker run --rm --network langfuse_net -p 3001:3000
   alpine sh -c "apk add socat && socat tcp-listen:3000,fork
   tcp:langfuse-web:3000"` (gambiarra).
3. **Mais simples — descomentar ports em dev**: editar localmente
   `docker-compose.langfuse.yml` voltando o bloco `ports: - "3001:3000"`
   no service `langfuse-web` e fazer `make langfuse-up`. NÃO commitar.

Em **Dokploy** (prod): Traefik roteia `langfuse.<domain>` → `langfuse-web:3000`
sem precisar de porta de host.

**RAM**: ClickHouse + Postgres dedicado + Minio + Redis pesam ~1.5GB. Por isso
a stack vive em `docker-compose.langfuse.yml` separado e não sobe junto com
`make up`. A network `langfuse_net` é isolada do compose principal.

---

## 2. Criar projeto + copiar API keys

1. Acessar pela URL escolhida no passo anterior (Traefik local com Domain,
   ou ad-hoc com `ports: 3001:3000` em dev).
2. Criar organização (ex: `nexus`) → projeto (ex: `whatsapp-langchain-dev`)
3. Settings → API Keys → **Create new API keys**
4. Copiar para o `.env` da aplicação principal:

   ```bash
   # Em dev local fora do compose Langfuse (host bare-metal):
   LANGFUSE_HOST=http://localhost:3001     # (se publicou porta ad-hoc)
   # Em dev rodando API/Worker dentro de um compose com rede compartilhada:
   # LANGFUSE_HOST=http://langfuse-web:3000
   # Em prod Dokploy:
   # LANGFUSE_HOST=https://langfuse.vsanexus.com

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

## 6. Produção (standalone — fora do Dokploy, reusando Traefik dele)

**Por que não via Dokploy como Compose service**: o Docker provider do
Traefik do Dokploy não consegue descobrir o container do langfuse-web
mesmo com labels corretas e network certa (bug específico do deployment ID
dele em alguns casos). Após 6 commits de tentativas, partimos pra abordagem
standalone: stack sobe via `docker compose` direto no host, e o Traefik
do Dokploy aprende a rota via **file provider** (`/etc/dokploy/traefik/dynamic/`).

Vantagem: zero acoplamento com a engine Dokploy. Reusa Traefik + Let's Encrypt
existentes. Funciona porque o `traefik.yml` do Dokploy tem:
```yaml
providers:
  file:
    directory: /etc/dokploy/traefik/dynamic
    watch: true
```

### 6.1 Setar DNS + clonar repo no host

```bash
# DNS: apontar langfuse.vsanexus.com → IP do host (ANTES do deploy, senão
# Let's Encrypt falha no HTTP-01 challenge).

# SSH no host Dokploy
sudo su
mkdir -p /opt/langfuse && cd /opt/langfuse
git clone https://github.com/viniciusandradde/whatsapp-langchain-full.git .
# OU: scp do docker-compose.langfuse.yml + traefik/langfuse.yml direto
```

### 6.2 Setar `.env` com secrets fortes

```bash
cat > /opt/langfuse/.env <<EOF
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)
LANGFUSE_SALT=$(openssl rand -hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)
LANGFUSE_PUBLIC_URL=https://langfuse.vsanexus.com
EOF

chmod 600 /opt/langfuse/.env
```

### 6.3 Subir o stack (compose plain, sem Dokploy)

```bash
cd /opt/langfuse
docker compose -f docker-compose.langfuse.yml --env-file .env up -d

# Aguardar ~90s
docker compose -f docker-compose.langfuse.yml ps
# Esperado: 5 serviços Up + 1 init Exited (0)
```

O container `langfuse-web` ataca AUTOMATICAMENTE na rede `dokploy-network`
(o compose declara ela como `external: true`). Traefik consegue alcançá-lo
via hostname interno `langfuse-web:3000` na mesma rede.

### 6.4 Registrar rota no Traefik do Dokploy

Copiar o arquivo dynamic do repo pra dentro do diretório que Traefik observa:

```bash
cp /opt/langfuse/traefik/langfuse.yml /etc/dokploy/traefik/dynamic/langfuse.yml
chmod 644 /etc/dokploy/traefik/dynamic/langfuse.yml

# Verificar que Traefik pegou (watch: true → recarrega em ~2s)
sleep 5
docker exec dokploy-traefik wget -qO- http://localhost:8080/api/http/routers 2>/dev/null \
  | grep -o '"name":"langfuse[^"]*"'
# Esperado:
# "name":"langfuse-web@file"
# "name":"langfuse-websecure@file"
```

### 6.5 Smoke externo

```bash
# Deve retornar 200 + JSON
curl -sI https://langfuse.vsanexus.com/api/public/health | head -3
curl -s https://langfuse.vsanexus.com/api/public/health
# {"status":"OK","version":"3.175.0"}
```

Abrir `https://langfuse.vsanexus.com` no navegador → tela **Sign up / Sign in** do Langfuse.

### 6.6 Bootstrap do painel + keys

1. Acessar https://langfuse.vsanexus.com → criar conta (1ª vira admin).
2. Criar organização `nexus-chat` + projeto `whatsapp-langchain-prod`.
3. **Project Settings → API Keys → Create new** → copiar `pk-lf-...` + `sk-lf-...`.

### 6.7 Conectar `chat.vsanexus.com` ao Langfuse

No service Dokploy do `chat.vsanexus.com` → **Environment** → adicionar:

```bash
LANGFUSE_HOST=https://langfuse.vsanexus.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_ENVIRONMENT=production
LANGFUSE_PROMPT_LABEL=production
```

**Redeploy** do service principal. Logs do worker devem mostrar
`langfuse_client_initialized host=https://langfuse.vsanexus.com`.

### 6.8 Subir prompts + smoke E2E

1. Painel Langfuse → Prompts → criar `system-prompt:<template_id>` pra
   cada agente do catálogo, label `production`.
2. Mandar mensagem real em `chat.vsanexus.com` (WhatsApp produção).
3. Painel → Traces → confirmar trace com `environment=production`, `model`,
   `tokens`, `tool_calls`, `prompt_version`.
4. Fechar atendimento → cliente responde CSAT 0-10 → trace ganha `score nps=N`.

### 6.9 Operação

```bash
# Logs
docker compose -f /opt/langfuse/docker-compose.langfuse.yml logs -f langfuse-web

# Restart só o web
docker compose -f /opt/langfuse/docker-compose.langfuse.yml restart langfuse-web

# Update pra nova versão Langfuse
cd /opt/langfuse
git pull
docker compose -f docker-compose.langfuse.yml pull
docker compose -f docker-compose.langfuse.yml up -d

# Backup volumes
docker run --rm \
  -v langfuse_langfuse_postgres_data:/data \
  -v $(pwd):/backup alpine \
  tar czf /backup/langfuse-postgres-$(date +%F).tar.gz /data
```

### 6.10 Caveats

- **Sem gerenciamento Dokploy**: o stack NÃO aparece na UI Dokploy. Logs,
  restart, env vars — tudo via SSH. Trade-off aceitável pra ter o serviço
  funcionando.
- **DNS challenge ACME**: Let's Encrypt usa HTTP-01 challenge (vide
  `traefik.yml` do Dokploy). DNS deve estar resolvendo pro IP do host
  **antes** do Traefik tentar emitir o cert.
- **Memória**: stack pesa ~1.5GB (ClickHouse é o maior). Se VPS justa,
  considere `LANGFUSE_SAMPLE_RATE=0.1` (10% sampling) ou Langfuse Cloud.
- **Volumes**: vivem no host (`docker volume ls | grep langfuse_`).
  Backup acima ou snapshot do disco.

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
