# Deploy no Railway

Guia completo para deploy do whatsapp-langchain no Railway, cobrindo topologia de serviços, rede interna, watch paths e todas as variáveis de ambiente necessárias.

## Topologia de Serviços

O projeto usa 4 serviços no Railway:

| Serviço  | Dockerfile            | Porta | Visibilidade | Réplicas | Domínio                       |
|----------|-----------------------|-------|--------------|----------|-------------------------------|
| API      | `Dockerfile.api`      | 8000  | Público      | 2        | `api-*.up.railway.app`        |
| Worker   | `Dockerfile.worker`   | ---   | Privado      | 1        | ---                           |
| Frontend | `Dockerfile.frontend` | 3000  | Público      | 1        | `frontend-*.up.railway.app`   |
| DB       | `Dockerfile.db`       | 5432  | Privado      | 1        | ---                           |

### API

Serviço público que recebe webhooks do Twilio e expõe o health check.

- **Rotas públicas:** `/webhook/twilio` e `/health`
- **Rotas protegidas:** `/api/*` requerem o header `INTERNAL_SERVICE_TOKEN`
- O Frontend se comunica com a API via rede interna do Railway (`http://api.railway.internal:8000`), nunca pelo domínio público
- **2 réplicas** para reduzir indisponibilidade durante redeploy e servir como exemplo de load balancing no curso

> **Nota:** o rate limit atual é em memória. Com 2 réplicas, o limite efetivo fica por instância, não global.

### Worker

Serviço privado que consome a fila de mensagens do PostgreSQL.

- Sem porta exposta --- não recebe requisições HTTP
- Faz polling na tabela de fila do banco para processar mensagens pendentes
- Executa os agentes LangGraph e envia respostas via Twilio

### Frontend

Admin Panel em Next.js, público para acesso dos administradores.

- Consome a API internamente via `http://api.railway.internal:8000`
- O `INTERNAL_SERVICE_TOKEN` garante que apenas o Frontend consegue chamar as rotas `/api/*`
- Conecta diretamente ao banco para o Better Auth (sessões, usuários, tokens)

### DB (PostgreSQL + pgvector)

Container customizado usando a imagem `pgvector/pgvector:pg16`.

- Acessível apenas pela rede interna (privado)
- Volume persistente montado em `/var/lib/postgresql/data`
- pgvector habilitado para memória semântica (extensão criada via migração SQL)
- **Não é um plugin nativo do Railway** --- usa `Dockerfile.db` com a imagem do pgvector

---

## Rede Interna (Reference Variables)

Os serviços se comunicam pela rede privada do Railway. Para que o dashboard visualize as conexões entre serviços, usamos **reference variables** (`${{service.VARIABLE}}`) em vez de strings hardcoded.

### Conexoes

```
                    +----------+
                    |    db    | (privado)
                    | pgvector |
                    +----+-----+
              +----------+----------+
              |          |          |
         +----v---+ +----v----+ +--v-------+
         |  api   | | worker  | | frontend |
         | :8000  | | (priv.) | | Next.js  |
         +----+---+ +---------+ +--+-------+
              |                    |
              |<-------------------+
              |   INTERNAL_API_URL
              |   (rede interna)
```

### DATABASE_URL (api, worker, frontend)

```
postgresql://${{db.POSTGRES_USER}}:${{db.POSTGRES_PASSWORD}}@${{db.RAILWAY_PRIVATE_DOMAIN}}:5432/${{db.POSTGRES_DB}}
```

Isso referência as variáveis do serviço `db` e resolve para algo como:

```
postgresql://postgres:SENHA@db.railway.internal:5432/whatsapp_langchain
```

### INTERNAL_API_URL (frontend)

```
http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000
```

Resolve para `http://api.railway.internal:8000`.

### Como setar via CLI

A CLI do Railway (`railway variables`) mostra os valores **resolvidos**, mas internamente o Railway armazena as referências. Para setar via CLI, use aspas simples para evitar que o shell interprete `${{}}` como substituição bash:

```bash
# DATABASE_URL com referências ao serviço db
railway variables --service api --set 'DATABASE_URL=postgresql://${{db.POSTGRES_USER}}:${{db.POSTGRES_PASSWORD}}@${{db.RAILWAY_PRIVATE_DOMAIN}}:5432/${{db.POSTGRES_DB}}'

# INTERNAL_API_URL com referência ao serviço api
railway variables --service frontend --set 'INTERNAL_API_URL=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000'
```

> **Por que não hardcodar?** Além da visualização no dashboard, se o Railway alterar hostnames internos ou credenciais do banco, as referências se atualizam automaticamente.

---

## Watch Paths

Watch paths controlam quais arquivos disparam redeploy de cada serviço. Sem eles, qualquer push na branch causa redeploy de todos os serviços --- mesmo que a mudança não afete aquele serviço.

Configurados via dashboard em **Service Settings > Source > Watch Paths**.

| Serviço      | Watch Paths                                                                                      | Motivo                               |
|--------------|--------------------------------------------------------------------------------------------------|--------------------------------------|
| **API**      | `src/whatsapp_langchain/server/**`, `src/whatsapp_langchain/shared/**`, `pyproject.toml`, `uv.lock`, `Dockerfile.api` | Código da API + dependências compartilhadas |
| **Worker**   | `src/whatsapp_langchain/worker/**`, `src/whatsapp_langchain/agents/**`, `src/whatsapp_langchain/shared/**`, `pyproject.toml`, `uv.lock`, `Dockerfile.worker` | Worker + agentes + dependências compartilhadas |
| **Frontend** | `frontend/**`                                                                                    | Isolado do backend                   |
| **DB**       | `db/**`, `Dockerfile.db`                                                                         | Migrações e imagem do Postgres       |

### Por que não usar `src/**` para tudo?

O diretório `src/whatsapp_langchain/` contém código de ambos os serviços:

```
src/whatsapp_langchain/
├── server/    # usado apenas pela API
├── worker/    # usado apenas pelo Worker
├── agents/    # usado apenas pelo Worker
└── shared/    # usado por API e Worker
```

Se ambos assistirem `src/**`, uma mudança em `server/` causaria redeploy do Worker (desnecessário), e vice-versa. Watch paths granulares evitam redeploys inúteis.

### Por que `db/**` não está nos watch paths da API/Worker?

Migrações SQL são executadas manualmente (`python db/migrate.py`), não durante o build dos serviços. Uma nova migração não deve triggerar redeploy automático --- você roda a migração separadamente e só faz redeploy se o código mudou.

> **Nota:** o Railway não suporta watch paths via `railway.toml` para múltiplos serviços no mesmo repo. A configuração é feita pelo dashboard, por serviço.

---

## RAILWAY_DOCKERFILE_PATH

Todo serviço que usa Dockerfile customizado **precisa** da variável `RAILWAY_DOCKERFILE_PATH` apontando para o arquivo correto.

```bash
railway variables --service api --set 'RAILWAY_DOCKERFILE_PATH=Dockerfile.api'
railway variables --service worker --set 'RAILWAY_DOCKERFILE_PATH=Dockerfile.worker'
railway variables --service frontend --set 'RAILWAY_DOCKERFILE_PATH=Dockerfile.frontend'
railway variables --service db --set 'RAILWAY_DOCKERFILE_PATH=Dockerfile.db'
```

Sem essa variável, o Railway usa o builder automático (Railpack), que tenta detectar o framework. No caso do serviço `db`, o Railpack detectava Python e falhava com "No start command was found" --- porque não há nenhum app Python para rodar, e sim um PostgreSQL.

---

## Migrações

O projeto tem dois mecanismos de migração que coexistem:

### 1. Automatica (startup da API)

Quando a API sobe, o `lifespan` executa `run_migrations()` antes de aceitar requisições. Esse mecanismo:

1. Cria a tabela `_migrations` se não existir (controle de estado)
2. Le todos os arquivos `.sql` de `db/migrations/` em ordem alfabética
3. Compara com os nomes já registrados na tabela `_migrations`
4. Aplica os pendentes e registra cada um

```python
# src/whatsapp_langchain/server/main.py (lifespan)
pool = await get_pool()
await run_migrations(pool)          # migrações SQL
await bootstrap_langgraph_schema()  # tabelas do checkpointer + store
```

Isso significa que **não é necessário rodar migrações manualmente** após um deploy --- a API cuida disso automaticamente.

### 2. Manual (script standalone)

O script `db/migrate.py` faz a mesma coisa, mas de forma síncrona e independente. Útil para:

- Rodar migrações sem subir a API
- Debugging local
- Aplicar migrações em ambientes sem a API rodando

```bash
# Local
python db/migrate.py

# No Railway (usando variáveis do serviço api)
railway run --service api python db/migrate.py
```

### Arquivos de migração

```
db/migrations/
├── 001_initial.sql                 # Schema da fila de mensagens
├── 002_media_processing_audit.sql  # Auditoria de mídia
├── 003_auth_schema.sql             # Schema de auth
└── 004_better_auth_tables.sql      # Tabelas do Better Auth
```

Para adicionar uma nova migração, crie um arquivo SQL com o próximo número sequencial (ex: `005_nova_feature.sql`). A ordem alfabética dos nomes determina a ordem de aplicação.

### Idempotência e réplicas

Ambos os mecanismos usam a tabela `_migrations` com constraint `UNIQUE` no nome do arquivo. Se a migração já foi aplicada, ela é ignorada silenciosamente.

Com 2 réplicas da API, ambas tentam rodar migrações no startup. O `CREATE TABLE IF NOT EXISTS` e a constraint `UNIQUE` protegem contra duplicatas na maioria dos casos. Em cenários de alta concorrência, uma das réplicas pode receber um erro de constraint e falhar o startup --- mas o retry do Railway resolve isso automaticamente.

### Bootstrap do LangGraph

Além das migrações SQL, o startup da API também executa `bootstrap_langgraph_schema()`, que inicializa:

- **Checkpointer** (`AsyncPostgresSaver`) --- tabelas para persistência de conversas
- **Store vetorial** (`AsyncPostgresStore`) --- tabelas para memória semântica (quando `MEMORY_ENABLED=true`)

Essas tabelas são do LangGraph e não aparecem em `db/migrations/`. O LangGraph gerencia o schema delas internamente via `.setup()`.

---

## Variáveis de Ambiente

Abaixo estão todas as variáveis necessárias, organizadas por serviço.

### DB

| Variavel | Valor / Exemplo | Descricao |
|----------|----------------|-----------|
| `POSTGRES_USER` | `postgres` | Usuario do PostgreSQL |
| `POSTGRES_PASSWORD` | --- | Senha do PostgreSQL (gerar com `openssl rand -base64 32`) |
| `POSTGRES_DB` | `whatsapp_langchain` | Nome do banco de dados |
| `PGDATA` | `/var/lib/postgresql/data/pgdata` | Diretorio de dados (dentro do volume) |
| `RAILWAY_DOCKERFILE_PATH` | `Dockerfile.db` | Aponta para o Dockerfile do container Postgres |

### API

| Variavel | Valor / Exemplo | Descricao |
|----------|----------------|-----------|
| `DATABASE_URL` | `${{db.*}}` (reference) | Connection string do PostgreSQL via rede interna |
| `ENVIRONMENT` | `production` | Ambiente de execução --- desabilita `/webhook/sync` em production |
| `LOG_LEVEL` | `info` | Nível de log (debug, info, warning, error) |
| `LOG_JSON` | `true` | Logs em formato JSON estruturado (melhor para produção) |
| `PORT` | `8000` | Porta do FastAPI |
| `VALIDATE_TWILIO_SIGNATURE` | `true` | Validar assinatura dos webhooks do Twilio |
| `TWILIO_AUTH_TOKEN` | --- | Token de autenticação do Twilio (necessário para validação de assinatura) |
| `TWILIO_WEBHOOK_URL` | `https://api-*.up.railway.app` | URL base pública da API (sem path) |
| `RATE_LIMIT_PER_HOUR` | `30` | Maximo de mensagens por telefone por hora |
| `MESSAGE_BUFFER_SECONDS` | `2.0` | Tempo de espera para agrupar mensagens consecutivas |
| `INTERNAL_SERVICE_TOKEN` | --- | Token para proteger rotas `/api/*` **(shared com Frontend)** |
| `OPENROUTER_API_KEY` | --- | Chave do OpenRouter (necessária para bootstrap do LangGraph store — embeddings) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | URL base do OpenRouter (idem) |
| `MEMORY_ENABLED` | `true` | Habilitar memória semântica — controla se o store vetorial é criado no startup |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Modelo de embeddings usado no bootstrap do store |
| `EMBEDDING_DIMS` | `1536` | Dimensões do vetor de embeddings |
| `RAILWAY_DOCKERFILE_PATH` | `Dockerfile.api` | Aponta para o Dockerfile da API |

> **Por que a API precisa de variáveis de embeddings?** No startup, a API chama `bootstrap_langgraph_schema()` que inicializa as tabelas do checkpointer e do store vetorial. O store precisa da configuração de embeddings para criar os índices. Sem essas variáveis, o startup falha quando `MEMORY_ENABLED=true`.

### Worker

| Variavel | Valor / Exemplo | Descricao |
|----------|----------------|-----------|
| `DATABASE_URL` | `${{db.*}}` (reference) | Connection string do PostgreSQL via rede interna |
| `ENVIRONMENT` | `production` | Ambiente de execução |
| `LOG_LEVEL` | `info` | Nível de log |
| `LOG_JSON` | `true` | Logs em formato JSON estruturado |
| `OPENROUTER_API_KEY` | --- | Chave de API do OpenRouter |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | URL base do OpenRouter |
| `OPENROUTER_MODEL` | --- | Modelo principal para o agente |
| `OPENROUTER_MIDIA_MODEL` | --- | Modelo para processamento de mídia |
| `TWILIO_ACCOUNT_SID` | --- | Account SID do Twilio |
| `TWILIO_API_KEY_SID` | --- | API Key SID para envio de mensagens e download de mídia |
| `TWILIO_API_KEY_SECRET` | --- | API Key Secret para envio de mensagens e download de mídia |
| `TWILIO_FROM_NUMBER` | `whatsapp:+14155238886` | Numero do WhatsApp remetente |
| `TWILIO_OUTBOUND_MODE` | `real` | Em produção, manter envio Twilio em modo real |
| `POLL_INTERVAL_SECONDS` | `1.0` | Intervalo de polling na fila |
| `LEASE_SECONDS` | `60` | Tempo máximo de processamento antes de retry |
| `MAX_ATTEMPTS` | `3` | Numero máximo de tentativas por mensagem |
| `MEDIA_IMAGE_ENABLED` | `true` | Habilitar processamento de imagens |
| `MEDIA_AUDIO_ENABLED` | `true` | Habilitar processamento de áudio |
| `LLM_RATE_LIMIT_REQUESTS_PER_SECOND` | `0.5` | Limite de requisições por segundo ao LLM |
| `LLM_RATE_LIMIT_MAX_BURST` | `10` | Maximo de requisições em rajada ao LLM |
| `CONTEXT_STRATEGY` | `summarize` | Estratégia de contexto do middleware |
| `TRIM_KEEP_TURNS` | `2` | Turnos a manter ao usar trim |
| `SUMMARIZE_TRIGGER_TOKENS` | `4000` | Tokens que disparam a sumarização |
| `SUMMARIZE_KEEP_MESSAGES` | `10` | Mensagens a manter após sumarizar |
| `SUMMARIZE_MODEL` | --- | Modelo usado para sumarização |
| `MEMORY_ENABLED` | `true` | Habilitar memória semântica |
| `MEMORY_SEARCH_LIMIT` | `5` | Maximo de memórias retornadas por busca |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Modelo de embeddings |
| `EMBEDDING_DIMS` | `1536` | Dimensões do vetor de embeddings |
| `RAILWAY_DOCKERFILE_PATH` | `Dockerfile.worker` | Aponta para o Dockerfile do Worker |

> O `TWILIO_AUTH_TOKEN` fica somente no serviço `api`, onde a assinatura
> inbound do webhook é validada. O worker usa `TWILIO_ACCOUNT_SID`,
> `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET` e `TWILIO_FROM_NUMBER`.

### Frontend

| Variavel | Valor / Exemplo | Descricao |
|----------|----------------|-----------|
| `DATABASE_URL` | `${{db.*}}` (reference) | Connection string do PostgreSQL (para Better Auth) |
| `ENVIRONMENT` | `production` | Ativa guard rails de produção no frontend |
| `INTERNAL_API_URL` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` | URL interna da API (rede privada Railway) |
| `INTERNAL_SERVICE_TOKEN` | --- | Token para autenticar nas rotas `/api/*` **(shared com API)** |
| `BETTER_AUTH_SECRET` | --- | Secret para sessões do Better Auth (gerar com `openssl rand -base64 32`) |
| `BETTER_AUTH_URL` | `https://frontend-*.up.railway.app` | URL pública do Frontend (usada pelo Better Auth para callbacks) |
| `ADMIN_EMAIL` | `admin@empresa.com` | Email do primeiro acesso ao painel |
| `ADMIN_PASSWORD` | --- | Senha do primeiro acesso ao painel; troque após o login inicial |
| `ADMIN_NAME` | `Admin` | Nome exibido do primeiro usuário (opcional) |
| `RAILWAY_DOCKERFILE_PATH` | `Dockerfile.frontend` | Aponta para o Dockerfile do Frontend |

---

## Bootstrap do primeiro admin

Se `auth."user"` estiver vazio, o primeiro acesso ao `/login` cria
automaticamente o primeiro admin usando `ADMIN_EMAIL` e `ADMIN_PASSWORD`
definidos no serviço `frontend`.

Fluxo recomendado:

```bash
# Service: frontend
ADMIN_EMAIL=admin@empresa.com
ADMIN_PASSWORD=uma-senha-forte-aqui
ADMIN_NAME=Admin
```

Depois disso:
- entre pelo `/login`
- valide acesso ao painel
- troque a senha no `/settings`

Opcional em ambientes compartilhados:
- remova ou rotacione `ADMIN_PASSWORD` depois do primeiro login

> O signup público do Better Auth fica desabilitado e as rotas `/api/auth/sign-up/*`
> retornam `404`.
> O frontend também falha cedo em production se `INTERNAL_SERVICE_TOKEN` ou
> `BETTER_AUTH_SECRET` estiverem fracos.

---

## Checklist de Deploy

1. Criar o projeto no Railway
2. Criar os 4 serviços (db, api, worker, frontend) apontando para o mesmo repo
3. Setar `RAILWAY_DOCKERFILE_PATH` em cada serviço
4. Configurar variáveis do DB (user, password, database, pgdata)
5. Configurar `DATABASE_URL` com reference variables nos 3 serviços
6. Configurar variáveis específicas de cada serviço (tabelas acima)
7. Gerar domínio público para API e Frontend
8. Atualizar `TWILIO_WEBHOOK_URL` com o domínio real da API
9. Atualizar `BETTER_AUTH_URL` com o domínio real do Frontend
10. Configurar watch paths por serviço (ver tabela acima)
11. Configurar 2 réplicas na API
12. Adicionar volume ao serviço DB (`/var/lib/postgresql/data`)
13. Verificar migrações (rodam automaticamente no startup da API --- checar logs por `migration_applying`)
14. Testar health check: `GET https://api-*.up.railway.app/health`
15. Definir `ADMIN_EMAIL` e `ADMIN_PASSWORD` no serviço `frontend`
16. Acessar `/login`, validar o bootstrap automático do primeiro admin e trocar a senha
16. Testar login no painel e navegação completa
17. Testar fluxo completo: mensagem WhatsApp -> fila -> worker -> resposta
