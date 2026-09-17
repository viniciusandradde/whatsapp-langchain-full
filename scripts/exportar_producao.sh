#!/usr/bin/env bash
# Export completo de produção — tudo que é preciso para levantar o Chat Nexus
# em OUTRA máquina, incluindo as sessões WhatsApp sem re-parear.
#
# Roda a partir da MÁQUINA DE DEV e puxa do host por SSH. Complementa o
# `backup_prod.sh` (que cuida só do banco da aplicação, diariamente): aqui
# entram o banco da Evolution, o banco do Dokploy, os envs dos containers e as
# configs do host — o conjunto que transforma servidor novo em produção.
#
#   ./scripts/exportar_producao.sh                 # export completo
#   DUMP_NOVO=1 ./scripts/exportar_producao.sh     # idem, mas gera o dump da app AGORA
#                                                  # (em vez de reusar o do timer das 03:15)
#   ./scripts/exportar_producao.sh --verificar DIR # prova que o snapshot presta
#   ./scripts/exportar_producao.sh --cifrar DIR    # empacota segredos com GPG
#   ./scripts/exportar_producao.sh --offsite DIR   # sobe o pacote cifrado ao Drive
#
# Por que cópia de arquivo NÃO substitui isto: `evolution_pgdata` e
# `dokploy-postgres` são volumes de bancos EM EXECUÇÃO. Copiados a quente por
# SFTP/rsync saem rasgados e não restauram. `pg_dump` sai de dentro do
# container, com consistência transacional.

set -euo pipefail

HOST="${HOST:-opc@100.116.235.14}"
DESTINO="${DESTINO:-$HOME/backups/chatnexus-export}"
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive:chatnexus-config}"

# Containers em produção. O do Dokploy tem sufixo de task do Swarm (muda a cada
# redeploy), então é descoberto por filtro em vez de fixado.
CT_APP_DB="chatnexus-hatvsanexus-nfcfwu-db-1"
CT_EVO_PG="compose-synthesize-optical-panel-k4cc2z-evolution-postgres-1"
CT_EVO_API="compose-synthesize-optical-panel-k4cc2z-evolution-api-1"
CTS_ENV=(
  "chatnexus-hatvsanexus-nfcfwu-api-1"
  "chatnexus-hatvsanexus-nfcfwu-worker-1"
  "chatnexus-hatvsanexus-nfcfwu-worker-2"
  "chatnexus-hatvsanexus-nfcfwu-frontend-1"
  "$CT_APP_DB"
  "$CT_EVO_API"
)

# `pg_restore` NÃO existe no host nem, necessariamente, no dev — a verificação
# roda dentro de um container descartável. Sem isso a checagem devolve 0
# objetos e parece falha de dump quando é falta de binário.
IMG_PG="postgres:16-alpine"

log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
erro() { printf '[%s] ERRO: %s\n' "$(date +%H:%M:%S)" "$*" >&2; }

# ---------------------------------------------------------------- export ----

exportar() {
  local ts out
  ts=$(date +%Y-%m-%d_%H%M)
  out="$DESTINO/$ts"
  mkdir -p "$out"/{dados,segredos,config}
  log "destino: $out"

  # 1. Banco da aplicação. Reusa o dump do dia se o timer já rodou (são ~2 GB;
  #    gerar de novo é caro e o do timer já passou pela verificação de integridade).
  local hoje remoto espelho
  hoje=$(date +%Y-%m-%d)
  remoto="/home/opc/backup/prod-$hoje.dump.zst"
  espelho="$HOME/backups/chatnexus-prod/prod-$hoje.dump.zst"

  if [ "${DUMP_NOVO:-0}" = "1" ]; then
    # O dump do timer é da madrugada; o espelho das 18h (backup_espelho_vps.sh)
    # quer o dia inteiro. Nome com hora pra não colidir com o do timer no host.
    log "1/7 banco da app — gerando AGORA (DUMP_NOVO=1)"
    remoto="/tmp/prod-$ts.dump.zst"
    ssh "$HOST" "sudo docker exec $CT_APP_DB pg_dump -U postgres -Fc whatsapp_langchain | zstd -q -T0 -o $remoto && sudo chown opc:opc $remoto"
    scp -q "$HOST:$remoto" "$out/dados/whatsapp_langchain.dump.zst"
    ssh "$HOST" "rm -f $remoto"
  elif [ -f "$espelho" ]; then
    # O cron das 04:30 já espelha o dump do dia aqui. Puxar os ~2 GB de novo
    # pela rede não acrescenta nada — e numa emergência o tempo é o recurso
    # escasso. Link rígido: ocupa zero a mais no disco.
    log "1/7 banco da app — reusando o espelho local (sem tráfego de rede)"
    ln -f "$espelho" "$out/dados/whatsapp_langchain.dump.zst" 2>/dev/null \
      || cp "$espelho" "$out/dados/whatsapp_langchain.dump.zst"
  else
    if ssh "$HOST" "test -f $remoto"; then
      log "1/7 banco da app — baixando o dump de hoje do host"
    else
      log "1/7 banco da app — gerando (o timer ainda não rodou hoje)"
      ssh "$HOST" "sudo docker exec $CT_APP_DB pg_dump -U postgres -Fc whatsapp_langchain | zstd -q -o /tmp/prod-$hoje.dump.zst && sudo chown opc:opc /tmp/prod-$hoje.dump.zst"
      remoto="/tmp/prod-$hoje.dump.zst"
    fi
    scp -q "$HOST:$remoto" "$out/dados/whatsapp_langchain.dump.zst"
  fi

  # 2. Banco da Evolution — é AQUI que moram as credenciais Baileys (tabela
  #    `Session`). O container da API não tem volume: perder este banco é
  #    re-parear todos os números.
  log "2/7 banco da Evolution (sessões WhatsApp)"
  ssh "$HOST" "sudo docker exec $CT_EVO_PG pg_dump -U evolution -Fc evolution" \
    > "$out/dados/evolution.dump"

  # 3. Banco do Dokploy — as variáveis de ambiente de produção de cada serviço.
  #    É o ".env" real; o repositório só tem `.env.example`.
  log "3/7 banco do Dokploy (variáveis de ambiente de produção)"
  local ct_dok
  ct_dok=$(ssh "$HOST" "sudo docker ps --filter name=dokploy-postgres --format '{{.Names}}' | head -1")
  [ -n "$ct_dok" ] || erro "container do dokploy-postgres não encontrado"
  ssh "$HOST" "sudo docker exec $ct_dok pg_dump -U dokploy -Fc dokploy" \
    > "$out/dados/dokploy.dump"

  # 4. Envs resolvidos dos containers. Só saem por `docker inspect` — no disco
  #    não existem em forma legível.
  log "4/7 envs dos containers"
  local c
  for c in "${CTS_ENV[@]}"; do
    ssh "$HOST" "sudo docker inspect $c --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null" \
      > "$out/segredos/env-$c.txt" || true
  done

  # 5. Configs do host: Dokploy, alertas, e a credencial do PRÓPRIO backup
  #    (sem o rclone.conf, restaurar em máquina nova deixa o offsite mudo).
  log "5/7 configs do host"
  ssh "$HOST" "sudo tar cz -C /etc dokploy" > "$out/config/etc-dokploy.tar.gz"
  ssh "$HOST" "sudo tar cz -C /etc/systemd/system \$(cd /etc/systemd/system && sudo ls -d chatnexus-*)" \
    > "$out/config/systemd-chatnexus.tar.gz"
  ssh "$HOST" "sudo cat /etc/chatnexus-monitor.env"        > "$out/segredos/chatnexus-monitor.env"
  ssh "$HOST" "sudo cat /root/.config/rclone/rclone.conf"  > "$out/segredos/rclone.conf"

  # 6. Inventário do que estava rodando — para reconstruir a stack igual.
  log "6/7 inventário de containers e imagens"
  ssh "$HOST" "sudo docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'"          > "$out/config/containers.txt"
  ssh "$HOST" "sudo docker image ls --digests --format '{{.Repository}}:{{.Tag}}\t{{.Digest}}'" > "$out/config/imagens.txt"
  ssh "$HOST" "sudo docker exec $CT_EVO_PG psql -U evolution -d evolution -t -A -F'|' -c 'SELECT name, \"ownerJid\", \"connectionStatus\" FROM \"Instance\" ORDER BY name'" \
    > "$out/config/instancias-evolution.txt" || true

  # 7. Manifesto com sha256 — é o que permite provar, do outro lado, que a
  #    cópia chegou inteira.
  log "7/7 manifesto"
  chmod -R go-rwx "$out/segredos"
  ( cd "$out" && find . -type f ! -name MANIFESTO.sha256 -exec sha256sum {} \; \
      | sort -k2 > MANIFESTO.sha256 )

  log "export concluído — $(du -sh "$out" | cut -f1) em $out"
  echo "$out"
}

# ------------------------------------------------------------ verificação ----

# Restaura cada dump numa base DESCARTÁVEL e confere o conteúdo. Verificar por
# tamanho de arquivo não prova nada: dump truncado também tem tamanho.
verificar() {
  local dir="${1:?uso: --verificar DIR}"
  local falhas=0 nome
  command -v docker >/dev/null || { erro "docker é necessário para verificar"; return 1; }

  log "subindo Postgres descartável para conferência"
  docker rm -f verifica-export >/dev/null 2>&1 || true
  docker run --rm -d --name verifica-export -e POSTGRES_PASSWORD=v \
    -v "$dir/dados:/d:ro" "$IMG_PG" >/dev/null
  # shellcheck disable=SC2064
  trap "docker rm -f verifica-export >/dev/null 2>&1 || true" RETURN
  until docker exec verifica-export pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done

  checa() { # nome | esperado | obtido
    if [ "$2" = "$3" ] || { [ "${4:-eq}" = "min" ] && [ "$3" -ge "$2" ] 2>/dev/null; }; then
      printf '  PASSA   %-42s %s\n' "$1" "$3"
    else
      printf '  REPROVA %-42s obtido=%s esperado=%s\n' "$1" "$3" "$2"; falhas=$((falhas+1))
    fi
  }

  # --- banco da aplicação: o mesmo critério do backup_prod.sh (<100 objetos
  #     = truncado). O arquivo vem comprimido, então descomprime antes.
  if [ -f "$dir/dados/whatsapp_langchain.dump.zst" ]; then
    docker exec verifica-export sh -c \
      'command -v zstd >/dev/null || (apk add --no-cache zstd >/dev/null 2>&1); zstd -dq -f /d/whatsapp_langchain.dump.zst -o /tmp/app.dump' >/dev/null 2>&1
    n=$(docker exec verifica-export sh -c 'pg_restore -l /tmp/app.dump 2>/dev/null | grep -c "^[0-9]"' || echo 0)
    checa "app: objetos no dump" 100 "$n" min
  fi

  # --- Evolution: a checagem que separa "tenho backup" de "tenho a sessão".
  docker exec verifica-export psql -U postgres -q -c 'CREATE DATABASE evo_teste' >/dev/null 2>&1
  docker exec verifica-export pg_restore -U postgres -d evo_teste --no-owner /d/evolution.dump >/dev/null 2>&1 || true
  n=$(docker exec verifica-export psql -U postgres -d evo_teste -t -A -c 'SELECT count(*) FROM "Session"' 2>/dev/null || echo 0)
  checa "evolution: linhas em Session" 2 "$n" min
  n=$(docker exec verifica-export psql -U postgres -d evo_teste -t -A -c 'SELECT count(*) FROM "Instance"' 2>/dev/null || echo 0)
  checa "evolution: instâncias" 2 "$n" min
  # Credencial vazia restaura sem erro e só falha na hora de conectar — por isso
  # confere BYTES, não só a presença da linha.
  n=$(docker exec verifica-export psql -U postgres -d evo_teste -t -A -c \
        'SELECT count(*) FROM "Session" WHERE creds IS NOT NULL AND length(creds) > 500' 2>/dev/null || echo 0)
  checa "evolution: credenciais Baileys com conteúdo" 2 "$n" min
  echo "  instâncias no dump:"
  docker exec verifica-export psql -U postgres -d evo_teste -t -A -F' | ' \
    -c 'SELECT name, "ownerJid" FROM "Instance" ORDER BY name' 2>/dev/null | sed 's/^/    /'

  # --- Dokploy: sem estas linhas, o servidor novo sobe sem as variáveis.
  docker exec verifica-export psql -U postgres -q -c 'CREATE DATABASE dok_teste' >/dev/null 2>&1
  docker exec verifica-export pg_restore -U postgres -d dok_teste --no-owner /d/dokploy.dump >/dev/null 2>&1 || true
  n=$(docker exec verifica-export psql -U postgres -d dok_teste -t -A -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo 0)
  checa "dokploy: tabelas restauradas" 5 "$n" min
  # Tabela restaurada não prova nada sozinha: o que faz o servidor novo virar
  # produção é a coluna `env` do compose, onde o Dokploy guarda as variáveis.
  # Restaurar o schema com `env` vazio passaria despercebido até o deploy falhar.
  n=$(docker exec verifica-export psql -U postgres -d dok_teste -t -A -c \
        "SELECT count(*) FROM compose WHERE env IS NOT NULL AND length(env) > 1000" 2>/dev/null || echo 0)
  checa "dokploy: env de produção com conteúdo" 1 "$n" min

  # --- integridade da transferência
  if [ -f "$dir/MANIFESTO.sha256" ]; then
    if ( cd "$dir" && sha256sum -c MANIFESTO.sha256 --quiet 2>/dev/null ); then
      printf '  PASSA   %-42s %s\n' "manifesto sha256" "todos conferem"
    else
      printf '  REPROVA %-42s %s\n' "manifesto sha256" "divergência"; falhas=$((falhas+1))
    fi
  fi

  # --- segredos presentes (sem imprimir valor)
  for nome in rclone.conf chatnexus-monitor.env; do
    if [ -s "$dir/segredos/$nome" ]; then
      printf '  PASSA   %-42s %s\n' "segredo: $nome" "presente"
    else
      printf '  REPROVA %-42s %s\n' "segredo: $nome" "AUSENTE"; falhas=$((falhas+1))
    fi
  done

  echo
  if [ "$falhas" -eq 0 ]; then
    log "VERIFICAÇÃO OK — o snapshot restaura, com as sessões WhatsApp íntegras"
    return 0
  fi
  erro "VERIFICAÇÃO REPROVOU em $falhas item(ns) — NÃO confie neste snapshot"
  return 1
}

# ----------------------------------------------------------------- cifrar ----

# Segredo de produção não sobe em claro para nuvem de terceiro. GPG simétrico
# (AES-256) porque não depende de par de chaves guardado em outro lugar — o que
# num desastre é exatamente o que some junto.
cifrar() {
  local dir="${1:?uso: --cifrar DIR}"
  local pacote="$dir/segredos-e-config.tar.gz.gpg"
  local senha_arq="$HOME/.secrets/export-producao-$(basename "$dir").pass"

  command -v gpg >/dev/null || { erro "gpg não instalado"; return 1; }
  mkdir -p "$HOME/.secrets"; chmod 700 "$HOME/.secrets"

  if [ ! -f "$senha_arq" ]; then
    ( umask 077; head -c 32 /dev/urandom | base64 > "$senha_arq" )
    log "senha gerada em $senha_arq (600) — guarde FORA deste servidor"
  fi

  tar cz -C "$dir" segredos config \
    | gpg --batch --yes --symmetric --cipher-algo AES256 \
          --passphrase-file "$senha_arq" -o "$pacote"
  chmod 600 "$pacote"
  log "pacote cifrado: $pacote ($(du -h "$pacote" | cut -f1))"

  gpg --batch --quiet --decrypt --passphrase-file "$senha_arq" "$pacote" >/dev/null 2>&1 \
    && log "conferido: o pacote abre com a senha gravada" \
    || { erro "o pacote NÃO abre — não envie"; return 1; }
  echo "$pacote"
}

# --------------------------------------------------------------- offsite ----

# O dev não tem rclone; o host tem, com o remoto `gdrive:` já autenticado.
# Sobe SÓ o pacote cifrado (poucos MB) — os dumps ficam no dev, porque o Drive
# está perto do limite e não comporta o snapshot inteiro.
enviar_offsite() {
  local dir="${1:?uso: --offsite DIR}"
  local pacote="$dir/segredos-e-config.tar.gz.gpg"
  [ -f "$pacote" ] || { erro "pacote cifrado não existe — rode --cifrar antes"; return 1; }
  local nome; nome="config-$(basename "$dir").tar.gz.gpg"

  log "enviando $nome via rclone do host"
  scp -q "$pacote" "$HOST:/tmp/$nome"
  # `sudo` não tem /usr/local/bin no secure_path: caminho absoluto obrigatório,
  # senão o rclone "não existe" com o binário ali.
  ssh "$HOST" "sudo /usr/local/bin/rclone copyto /tmp/$nome $RCLONE_REMOTE/$nome && rm -f /tmp/$nome"
  # Confirma no destino: exit code do copy sozinho já enganou aqui antes.
  if ssh "$HOST" "sudo /usr/local/bin/rclone lsf $RCLONE_REMOTE/$nome" >/dev/null 2>&1; then
    log "confirmado no destino: $RCLONE_REMOTE/$nome"
  else
    erro "o arquivo NÃO apareceu em $RCLONE_REMOTE"; return 1
  fi
}

# -------------------------------------------------------------------- cli ----

case "${1:-}" in
  --verificar) verificar "${2:?informe o diretório}" ;;
  --cifrar)    cifrar    "${2:?informe o diretório}" ;;
  --offsite)   enviar_offsite "${2:?informe o diretório}" ;;
  -h|--help)   sed -n '2,20p' "$0" ;;
  "")          exportar ;;
  *)           erro "opção desconhecida: $1"; exit 2 ;;
esac
