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
Frontend   cd frontend && npm run dev
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

### Levar uma mudança de `src/` até a produção

1. Trabalhe em branch. Nunca commite direto em `master` — é o gatilho do
   deploy.
2. `make ci` (lint + tipos + testes) e `make check-web` passando.
3. **Se a mudança tem migration**, ensaie a restauração antes:
   `scripts/backup_prod.sh --restaurar <backup> ensaio_migration`, aplique lá,
   confira. Migration que derruba coluna vai **depois** do deploy do código
   que parou de usar — a ordem inversa é outage esperando tráfego (lição do
   incidente I1).
4. Abra PR. O merge em `master` dispara `deploy.yml`, que publica no registry
   e manda o Dokploy recriar.
5. Depois do deploy: `docker logs ...-worker-1 --since 10m | grep -i error` e
   confira a fila.

---

## Backup de produção

Instalado junto, porque a migração descobriu que não existia:

```bash
sudo scripts/backup_prod.sh --instalar   # timer systemd, 03:15 diário
scripts/backup_prod.sh                   # roda uma vez pra validar
```

Guarda 14 dias em `/var/backups/chatnexus`, confere que o dump é legível
(`pg_restore -l`) e apaga o que passou da retenção. Restaurar sempre cria uma
base nova — nunca sobrescreve a produção.

> **Limitação:** tudo vive no mesmo host. Protege contra erro humano e
> migration ruim, que são as causas prováveis. **Não** protege contra perder o
> servidor. Fechar isso precisa de destino externo e é decisão de custo.

---

## Problemas conhecidos

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

**Porta 5434, 8081 ou 3081 ocupada.** Ajuste em `docker-compose.override.yml`
e no `.env`.
