# Migrar o desenvolvimento para a máquina local

Como sair do VPS e desenvolver na sua máquina, **sem derrubar quem usa o
sistema**.

A produção continua onde está. O que muda de lugar é o ambiente de trabalho:
repositório, banco, containers, e o histórico do Claude.

---

## Por que

O trabalho de frontend acabou. O que sobra mexe em `src/` — rotas, worker,
migrations — e `src/` é o que sustenta o cliente. O levantamento de
2026-07-31 mediu o risco de continuar desenvolvendo no VPS:

| fato | consequência |
|---|---|
| 1.573 mensagens/semana da empresa 1018, conexão em modo `ia` | tráfego real, respondido automaticamente |
| A API roda o migrator no boot (`server/main.py:189`) | subir um uvicorn local apontado pro banco de produção aplica DDL nele. **Já aconteceu** — ver [defeitos.md](benchmark/nosso-painel/defeitos.md) I1 |
| `.env` tem `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE_NAME` reais | um worker de teste manda WhatsApp de verdade pra pessoa de verdade |
| 3,2 GB de RAM livres, 2,7 GB já em swap | produção usa 780 MB; o `next dev` sozinho usa 4 GB |
| Zero backup | nenhum |

---

## Pré-requisitos

1. **Máquina Ubuntu ou Debian, x86_64.** As imagens Docker do VPS são ARM e
   não servem — o script recompila do código, o que é mais confiável de todo
   jeito.
2. **Tailscale na mesma tailnet do VPS.** É por onde os ~2 GB passam.
   `sudo tailscale up` e autorize com a mesma conta. Confira com
   `tailscale status | grep vps-docker03`.
3. **~10 GB livres**: 2 GB do pacote, 2,4 GB de dependências reinstaladas,
   e as imagens Docker.

---

## Os quatro passos

### 1. Exportar (no VPS)

```bash
cd /home/dev/projetos/chatnexus
scripts/migrar-dev/00-exportar.sh
```

Monta `/tmp/chatnexus-migracao/`:

| arquivo | o que é |
|---|---|
| `prod.dump` | backup íntegro da produção — **contém PII, guarde como o banco** |
| `dev.dump` | cópia saneada, ~10 MB, sem telefone, documento, conversa ou credencial |
| `repo.tar.zst` | repositório com `.git` e as 261 capturas do benchmark |
| `claude.tar.zst` | histórico, memórias e planos |
| `segredos.tar.zst` | `.env` e `frontend/.env.local`, `chmod 600` |
| `MANIFESTO.txt` | tamanho e `sha256` de cada peça |

O script **só lê** da produção. Ele para sozinho se o saneamento falhar — é
melhor não exportar do que exportar dado de cliente.

### 2. Preparar a máquina (no Ubuntu)

```bash
scripts/migrar-dev/01-preparar-maquina.sh
```

Instala Docker Engine + compose v2 (do repositório oficial, não o `docker.io`
do apt), `uv`, Node 22, `postgresql-client-16`, Tailscale. Idempotente.

> Se ele te adicionar ao grupo `docker`, **saia e entre na sessão** antes do
> passo 3.

### 3. Importar (no Ubuntu)

```bash
scripts/migrar-dev/02-importar.sh vps-docker03:/tmp/chatnexus-migracao
```

Baixa, confere `sha256`, extrai, **aplica e verifica o contrato de
isolamento**, sobe o stack e restaura o banco.

### 4. Conferir

O próprio script termina verificando. Quando ele diz "Ambiente de
desenvolvimento no ar":

```
API        http://localhost:8081
Banco      postgresql://postgres:postgres@localhost:5434/whatsapp_langchain
Frontend   cd frontend && npm run dev   → :3100
```

---

## Contrato de isolamento

Seis travas, aplicadas no `.env` pelo importador e **verificadas antes de o
worker subir**. Se alguma falhar, nada é levantado.

| # | trava | por quê |
|---|---|---|
| 1 | `DATABASE_URL` aponta pra `localhost:5434` | a API roda migrations no boot; apontar pra produção aplica DDL lá |
| 2 | `EVOLUTION_OUTBOUND_MODE=mock` e `TWILIO_OUTBOUND_MODE=mock` | **a que mais importa** — mesmo que todo o resto falhe, nada sai pra telefone real |
| 3 | webhook não apontado pro dev | a Evolution posta pra URL do VPS; o dev nunca é chamado |
| 4 | trabalho em branch, `master` intocado | `deploy.yml` dispara em push pra `master` e recria produção via Dokploy |
| 5 | `LANGFUSE_ENABLED=false` | traces de teste não entram no painel de produção |
| 6 | `LLM_RATE_LIMIT_REQUESTS_PER_SECOND=1` | a chave do OpenRouter é a mesma e gasta de verdade |

A **segunda linha de defesa** é o próprio banco: `sanitizar_dev.sql` zera
`conexao.credentials_encrypted`, `payload_json.instance_name` e as chaves de
API. Mesmo trocando a trava 2 pra `real`, não há com o que autenticar.

### Conferir a qualquer momento

```bash
cd ~/projetos/chatnexus
grep -cE '^(EVOLUTION|TWILIO)_OUTBOUND_MODE=mock$' .env   # 2
grep -E '^DATABASE_URL=' .env                             # localhost:5434

psql postgresql://postgres:postgres@localhost:5434/whatsapp_langchain -c "
  select (select count(*) from cliente where telefone not like '55119%') as tel_real,
         (select count(*) from checkpoints)                              as checkpoints,
         (select count(*) from conexao where credentials_encrypted is not null) as cred;"
# tudo zero
```

---

## O que o saneamento faz

`scripts/migrar-dev/sanitizar_dev.sql`. Roda sempre sobre uma restauração
descartável, nunca contra produção.

**Apaga o que não dá pra anonimizar** — 715 MB dos 1.122 MB do banco:
`checkpoints`, `checkpoint_blobs`, `checkpoint_writes` (conversa serializada
em binário), `store` e `store_vectors` (memória semântica e os embeddings
dela), `message_queue` (355 MB, mídia em base64), `audit_log` (replica em JSON
o antes/depois de tudo), sessões e tokens de reset.

**Embaralha preservando o formato** — telefone continua com cara de telefone
e CPF com cara de CPF, senão o ambiente para de exercitar as validações de
`lib/br-validators` e o lookup do nono dígito. A semente é o `id`, então o
mesmo registro gera sempre o mesmo valor falso e as junções continuam
fazendo sentido.

**Zera credenciais**: `conexao.credentials_encrypted`, `webhook_verify_token`,
`qr_code`, `payload_json.instance_name`, `empresa_api_key.key_hash`, senhas
bcrypt e tokens OAuth do Google, IDs do Asaas.

**Preserva de propósito**: `empresa`, `agente_ia`, `perfil_acesso`,
`permissao`, `menu_*`, `workflow_*`, `documento_conhecimento*`, `modelo_llm`,
`tag`. É configuração do produto — e é o que você precisa pra desenvolver.

> **Duas coisas continuam legíveis, e é bom você saber.**
>
> **Nome de empresa e prompt do agente.** "Hospital Mackenzie Dourados" segue
> lá, e o `prompt_override` pode citar o nome do cliente. É a sua relação
> comercial, não dado do cliente final.
>
> **A base de conhecimento viaja inteira** — `documento_conhecimento` e seus
> chunks. Sem ela não dá pra mexer em RAG, que é justamente o próximo
> trabalho (G4). Mas são os documentos que o cliente subiu; no caso do
> hospital, documentos de hospital. Se preferir que não viajem, o SQL tem um
> bloco pronto e comentado na seção 5 — descomente e reexporte.

### As checagens

O SQL termina com `RAISE EXCEPTION` se sobrou telefone, JID, `thread_id`,
credencial ou checkpoint — e falha se aparecer **coluna nova** com nome de
telefone ou JID que ninguém tratou. O exportador ainda varre o dump inteiro
em texto atrás de telefone brasileiro fora do padrão falso.

As duas camadas existem porque a primeira não bastou. Durante a construção,
a checagem por coluna passou limpa enquanto o grep no dump encontrava **oito**
vazamentos que nome de coluna nenhum denunciava:

| onde | por que escapou |
|---|---|
| `contato_capturado.wa_jid` | JID é `{telefone}@s.whatsapp.net` — o número está dentro |
| `conversations.thread_id` | é `"{telefone}:{agente}"` |
| `conexao.payload_json` | `instance_name` da Evolution, dentro de um JSON |
| `atendimento.resumo_ia` | resumo da conversa escrito pela IA |
| `rag_query_log.query_text` | a pergunta literal do cliente, 6.627 linhas |
| `cliente_memoria.created_by_user_id` | vale `agente:+5567...` quando quem agiu foi a IA |
| `grupo.nome` | grupos pessoais capturados: "Somos FAMÍLIA!", "Primos Amados" |
| `guardrail_log.sample` | o trecho que disparou o bloqueio, com telefone dentro |

Se você adicionar tabela com PII, trate no SQL. As checagens vão te avisar —
mas só depois que o grep pegar.

---

## Depois da migração

### Atualizar o banco de dev

O banco de dev envelhece. Para renovar:

```bash
# no VPS
scripts/migrar-dev/00-exportar.sh /tmp/refresh
# na sua máquina
rsync -avh vps-docker03:/tmp/refresh/dev.dump /tmp/
pg_restore -d postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
  --no-owner --no-acl --clean --if-exists /tmp/dev.dump
```

### Expurgar o Baileys da história do git

Apagar a pasta `docs/Baileys` liberou 672 MB da árvore de trabalho, mas o
`.git` continuou com **1,8 GB**: os arquivos estão na história, em dois
commits que os adicionaram. Git não esquece por deleção.

É a razão de `repo.tar.zst` ser o item mais pesado da transferência.

```bash
scripts/migrar-dev/expurgar-baileys.sh
```

Recupera ~1,75 GB — o `.git` cai para menos de 100 MB. Mas **reescreve a
história**: todo commit a partir de `9b95c15` ganha SHA novo, e esse commit
**já está em `origin/master`**. Consequências:

- `git push` normal passa a ser rejeitado; exige `--force-with-lease`.
- Qualquer outra cópia do repositório fica divergente e precisa re-clonar.
- PR aberto aponta pra commits que deixam de existir.

Por isso o script faz um espelho antes, pede confirmação, **remove o remote**
ao terminar e não faz push — te mostra o comando e deixa a decisão com você.

Faça isso **depois** de a migração estar validada, e só quando não houver
outra cópia viva do repositório.

### O dia a dia

O repositório de trabalho passa a ser **um só**: `/home/projects/chatnexus` na
máquina Ubuntu. O do VPS vira leitura até ser aposentado (seção abaixo) — com
duas cópias vivas, commitar dos dois lados diverge e o merge duplica commits.

```bash
cd /home/projects/chatnexus

# sobe o stack (quatro serviços, frontend incluído)
docker compose -p chatnexus-dev -f docker-compose.yml -f docker-compose.override.yml up -d

# painel  http://10.10.1.105:3100      login admin@dev.local
# API     http://10.10.1.105:8081
# logs    docker compose -p chatnexus-dev logs -f api worker
# parar   docker compose -p chatnexus-dev down
```

Mudou código Python: `docker compose -p chatnexus-dev up -d --build api worker`
— restart não pega edit, a imagem precisa ser refeita. Para iterar em UI com
recarga automática, `cd frontend && npm run dev` (porta 3100) em vez do
container.

Antes de abrir PR: `make check` (lint + tipos) e `make check-web`. **Não rode
`make ci` aqui** — ele inclui a suíte, que trava para sempre nesta máquina;
os testes rodam no GitHub Actions. O porquê está em "A suíte não termina
localmente", mais abaixo.

### Levar uma mudança de `src/` até a produção

O push agora sai da máquina de desenvolvimento; a produção continua sendo
recriada pelo Dokploy a partir do registry, sem ninguém compilar no VPS.

1. Trabalhe em branch. Nunca commite direto em `master` — é o gatilho do
   deploy.
2. `make check` (lint + tipos) e `make check-web` passando **na sua máquina** —
   não `make ci`, pela razão da seção "A suíte não termina localmente". Os
   testes ficam com o `ci.yml` no PR.
3. **Se a mudança tem migration**, ensaie a restauração antes:
   `scripts/backup_prod.sh --restaurar <backup> ensaio_migration`, aplique lá,
   confira. Migration que derruba coluna vai **depois** do deploy do código
   que parou de usar — a ordem inversa é outage esperando tráfego (lição do
   incidente I1).
4. `git push -u origin <branch>` e abra PR. O merge em `master` dispara
   `deploy.yml`, que publica no registry e manda o Dokploy recriar.
5. Depois do deploy: `docker logs ...-worker-1 --since 10m | grep -i error` e
   confira a fila. **Deploy verde não é migration aplicada** — as migrations
   rodam no boot da API, então espere o container *novo* (id diferente) ficar
   healthy; o antigo segue healthy e dá falso negativo.

> **`feat/shadcn-onda-0` nunca foi para o GitHub**, por decisão de 30/07: ela
> muda a aparência de ~200 arquivos e `master` recria o painel que atende
> cliente real. Hoje ela existe em duas cópias locais e em nenhum servidor —
> o `git push` dela é uma decisão consciente, não parte do fluxo acima. Se for
> expurgar o Baileys da história, faça **antes** de publicá-la: o expurgo
> reescreve SHAs e exigiria `--force-with-lease` num branch já publicado.

### Os gates do GitHub Actions

Nada de CI roda na sua máquina nem no VPS: os checks continuam no GitHub, e o
que você roda localmente (`make ci`, `make check-web`) é o mesmo conteúdo,
adiantado. O que muda com a migração é que agora **existe** um gate de backend.

| workflow | quando dispara | o que roda |
|---|---|---|
| `ci.yml` | push e **PR**, quando mexe em `src/`, `tests/`, `pyproject.toml`, `uv.lock` | `ruff check`, `ruff format --check`, `pyright src/`, `pytest` com gate de cobertura 50% |
| `frontend.yml` | push e **PR**, quando mexe em `frontend/` | `npm ci`, lint, `typecheck`, `build`, métricas de UI |
| `deploy.yml` | push em `master` | builda as imagens, publica no registry e manda o Dokploy recriar — **não roda teste** |
| `android.yml` | push que toca o app | build do APK |

O `ci.yml` é novo. Até então o único workflow que tocava o backend era o
`deploy.yml`, que não roda teste nenhum: o check verde queria dizer "a imagem
compilou", não "o código está correto" — e como ele só dispara em `master`, a
informação chegava depois de já estar em produção.

Os dois gates rodam em `ubuntu-latest`, amd64 nativo. A build de produção
continua sendo arm64 (o VPS é `aarch64`) e é feita pelo `deploy.yml` via
cross-compile, fora do servidor — foi o que tirou o build de cima da produção.

**Cuidado com o token**: um Personal Access Token sem o escopo `workflow` faz
o `git push` ser recusado quando o commit toca `.github/workflows/`. O erro
não diz isso com clareza.

### Aposentar o desenvolvimento no VPS

O objetivo da migração só se completa quando o VPS deixa de ter árvore de
trabalho: enquanto existir um repositório lá, existe a tentação de rodar
`uvicorn`/`pytest` apontando pro banco de produção — que é exatamente o
incidente I1.

Antes de apagar qualquer coisa, prove que nada ficou só no VPS:

```bash
# no VPS — algum commit que a máquina de desenvolvimento não tem?
git -C /home/dev/projetos/chatnexus log --all --oneline | sort > /tmp/vps.txt
# na máquina de desenvolvimento
git -C /home/projects/chatnexus log --all --oneline | sort > /tmp/dev.txt
comm -23 /tmp/vps.txt /tmp/dev.txt      # vazio = nada exclusivo do VPS
```

Compare por **lista**, nunca por contagem. Confira também o que o `.gitignore`
esconde e por isso não aparece no git — `.env`, `frontend/.env.local`,
`docker-compose.override.yml` e as capturas do benchmark. Só então:

```bash
sudo rm -rf /home/dev/projetos/chatnexus /home/dev/projetos/whatsapp-langchain
```

O que **fica** no VPS: os containers do Dokploy (`projetos-chatvsanexus-er02mp-*`),
`/etc/dokploy`, o backup em `/home/dev/backup` e o timer que o alimenta.
Nenhum deles depende da árvore de trabalho — o Dokploy puxa imagem do
registry, não compila do diretório.

---

## Backup de produção

Instalado junto, porque a migração descobriu que não existia:

```bash
sudo scripts/backup_prod.sh --instalar   # timer systemd, 03:15 diário
scripts/backup_prod.sh                   # roda uma vez pra validar
```

Guarda 14 dias em `/home/dev/backup`, confere que o dump é legível
(`pg_restore -l`) e apaga o que passou da retenção. Restaurar sempre cria uma
base nova — nunca sobrescreve a produção.

> **Limitação:** tudo vive no mesmo host. Protege contra erro humano e
> migration ruim, que são as causas prováveis. **Não** protege contra perder o
> servidor. Fechar isso precisa de destino externo e é decisão de custo.

---

## Problemas conhecidos

**A suíte não termina localmente.** `make ci` e `make test` somem por 30+
minutos. Não é lentidão: `tests/integration/test_conexoes_endpoints.py::TestSmokeWebhookWABA::test_post_webhook_aceita_payload_vazio_200`
trava para sempre, e reproduz sozinho.

A causa é a soma de duas coisas. O `_client()` do arquivo devolve
`TestClient(app)` **sem `with`**, então cada request cria e destrói um portal
do anyio, sem lifespan. E `waba_webhook_post` chama `get_pool()`
(`server/routes/webhook_waba.py:142`) **antes de saber se há algo a
processar** — o `{"object": "page"}` do teste chega lá. O pool nasce preso ao
event loop efêmero daquele request, ninguém o fecha, e o `join` do portal
espera tasks que nunca terminam.

Só aparece **quando o Postgres está acessível**: com o banco de pé em
`localhost:5434`, o pool abre e prende; sem banco, `get_pool()` estoura rápido
e o teste passa. Por isso era um mistério enquanto o desenvolvimento não tinha
banco local.

**Decisão: não perseguir isso localmente.** Rode `make check` (lint + tipos),
`make check-web` e arquivos dirigidos (`uv run pytest tests/unit/test_x.py`);
a suíte inteira é responsabilidade do `ci.yml`, que roda sem Postgres e por
isso não trava. O diagnóstico está registrado caso um dia valha corrigir —
os caminhos seriam fechar o pool numa fixture `autouse`, ou mover o
`get_pool()` do handler para depois da validação do payload.

**`docker` pede sudo depois do passo 2.** Você entrou no grupo `docker` mas a
sessão é antiga. Saia e entre.

**`pg_restore: unsupported version`.** O cliente é mais antigo que o servidor
16. `psql --version` deve dizer 16 ou mais.

**O Claude não acha o histórico.** O diretório em `~/.claude/projects/` é
nomeado pelo caminho do projeto. Se você instalou fora de
`/home/dev/projetos/chatnexus`, renomeie para o padrão do novo caminho
(barras viram hífens).

**Frontend não fala com a API.** `INTERNAL_API_URL` precisa existir no
**build**, não só no runtime — `output: "standalone"` congela a destination do
rewrite no route-manifest. Ver o aviso em [CLAUDE.md](../CLAUDE.md).

**Porta ocupada.** O stack usa 5434 (banco), 8081 (API) e 3100 (frontend).
Confira antes de importar — numa máquina com outros projetos, 3000 e 8080
costumam estar tomadas:

```bash
for p in 5434 8081 3100; do (echo >/dev/tcp/127.0.0.1/$p) 2>/dev/null \
  && echo "$p OCUPADA" || echo "$p livre"; done
```

Ajuste em `docker-compose.override.yml` (banco e API) e em
`frontend/.env.local` (`PORT`, `BETTER_AUTH_URL`) mais `FRONTEND_ORIGINS` no
`.env`. `docker ps` não basta: serviço fora do Docker não aparece lá.
