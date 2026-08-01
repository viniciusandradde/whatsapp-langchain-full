#!/usr/bin/env bash
#
# Consulta SOMENTE-LEITURA ao banco de produção, para pré-voo de release.
#
# Existe porque "prometo que só vou ler" não é garantia. Aqui a leitura é
# imposta em duas camadas independentes:
#
#   1. LOCAL — a consulta é recusada antes de sair desta máquina se não
#      começar com SELECT/WITH, se tiver mais de um comando, ou se contiver
#      verbo de escrita/DDL.
#   2. POSTGRES — a sessão abre com `default_transaction_read_only=on`. Toda
#      escrita e todo DDL falham com "cannot execute ... in a read-only
#      transaction", mesmo que a camada 1 tenha deixado passar.
#
# Limite honesto: a camada 2 é uma trava contra ERRO, não contra intenção.
# Quem conecta é o `postgres` (superusuário), e superusuário consegue
# desligar o GUC com `SET transaction_read_only = off`. Por isso a camada 1
# recusa `SET`. Para uma fronteira dura contra intenção, o caminho é um ROLE
# somente-leitura no banco — ver o rodapé.
#
# Uso:
#   scripts/prod_readonly.sh "SELECT template_catalog, count(*) FROM agente_ia GROUP BY 1"
#   scripts/prod_readonly.sh -f consulta.sql
#
set -euo pipefail

HOST="${PROD_SSH:-opc@100.67.148.26}"        # vps-docker03, via Tailscale
CONTAINER="${PROD_DB_CONTAINER:-projetos-chatvsanexus-er02mp-db-1}"
DB="${PROD_DB:-whatsapp_langchain}"
DBUSER="${PROD_DB_USER:-postgres}"

if [ "${1:-}" = "-f" ]; then
    [ -f "${2:-}" ] || { echo "arquivo não encontrado: ${2:-}" >&2; exit 2; }
    sql="$(cat "$2")"
else
    sql="${1:-}"
fi
[ -n "$sql" ] || { echo "uso: $0 'SELECT ...'  |  $0 -f arquivo.sql" >&2; exit 2; }

# ---------------------------------------------------------------------------
# Camada 1 — recusa antes de sair daqui
# ---------------------------------------------------------------------------

# Remove comentários de linha antes de analisar: um `-- conta do cliente` não
# pode derrubar a consulta, e um verbo escondido em comentário não pode passar.
sem_comentario="$(printf '%s\n' "$sql" | sed 's/--.*$//')"

# Neutraliza literais entre aspas simples ANTES da varredura de verbos. Sem
# isto, `WHERE action = 'agente.update'` é recusado por conter "update" — e o
# verbo ali é DADO, não comando: o Postgres nunca vai executá-lo. Só o texto
# analisado muda; o que vai pro servidor continua sendo a consulta original.
sem_literal="$(printf '%s' "$sem_comentario" | sed "s/'[^']*'/''/g")"

# 1a. Precisa COMEÇAR com SELECT ou WITH.
primeiro="$(printf '%s' "$sem_literal" | tr '\n' ' ' \
            | sed 's/^[[:space:]]*//' | cut -d' ' -f1 | tr '[:lower:]' '[:upper:]')"
case "$primeiro" in
    SELECT|WITH) ;;
    *) echo "RECUSADO: a consulta precisa começar com SELECT ou WITH (veio: '$primeiro')." >&2
       exit 1 ;;
esac

# 1b. Um comando só. `;` no meio abriria espaço pra emendar escrita.
# O envio usa o texto ORIGINAL; a análise usa a versão sem literais, pra um
# ponto-e-vírgula dentro de string não ser confundido com fim de comando.
corpo="$(printf '%s' "$sem_comentario" | sed 's/[[:space:]]*;[[:space:]]*$//')"
analise="$(printf '%s' "$sem_literal" | sed 's/[[:space:]]*;[[:space:]]*$//')"
if printf '%s' "$analise" | grep -q ';'; then
    echo "RECUSADO: mais de um comando (';' no meio). Rode um por vez." >&2
    exit 1
fi

# 1c. Nenhum verbo de escrita ou DDL em lugar nenhum — cobre também CTE que
#     modifica dado (`WITH x AS (DELETE ... RETURNING)`), que passaria em 1a.
proibidos='insert|update|delete|truncate|drop|alter|create|grant|revoke|comment|copy|vacuum|reindex|refresh|cluster|lock|notify|listen|unlisten|prepare|deallocate|call|do|set|reset|begin|commit|rollback|savepoint|discard|security'
if printf '%s' "$analise" | grep -qiE "\\b($proibidos)\\b"; then
    achado="$(printf '%s' "$analise" | grep -oiE "\\b($proibidos)\\b" | head -1)"
    echo "RECUSADO: verbo fora do contrato de leitura ('$achado')." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Camada 2 — Postgres impõe do outro lado
# ---------------------------------------------------------------------------
# `statement_timeout`: consulta ruim não pode prender produção.
# `idle_in_transaction_session_timeout`: sessão não pode segurar lock se a
# rede cair no meio.
OPCOES="-c default_transaction_read_only=on -c statement_timeout=30s -c idle_in_transaction_session_timeout=15s"

printf '%s\n' "$corpo" | ssh -o BatchMode=yes "$HOST" \
    "sg docker -c 'docker exec -i -e PGOPTIONS=\"$OPCOES\" $CONTAINER \
        psql -U $DBUSER -d $DB -v ON_ERROR_STOP=1 -P pager=off -f -'"

# ---------------------------------------------------------------------------
# Se algum dia precisar de fronteira dura (contra intenção, não contra erro),
# o caminho é criar um role no banco de produção — UMA vez, por quem tem
# autoridade pra isso:
#
#   CREATE ROLE claude_ro LOGIN PASSWORD '...' NOSUPERUSER NOCREATEDB NOCREATEROLE;
#   GRANT CONNECT ON DATABASE whatsapp_langchain TO claude_ro;
#   GRANT USAGE ON SCHEMA public, auth TO claude_ro;
#   GRANT SELECT ON ALL TABLES IN SCHEMA public, auth TO claude_ro;
#   ALTER ROLE claude_ro SET default_transaction_read_only = on;
#
# Aí `PROD_DB_USER=claude_ro` e nem superusuário nem erro de script conseguem
# escrever. Atenção: com RLS STRICT (mig 102), um role comum enxerga só o que
# `app.empresa_id` permitir — para consulta cross-empresa seria preciso
# `BYPASSRLS`, o que reabre parte do risco. Por isso o pré-voo roda como
# `postgres` com as travas acima.
