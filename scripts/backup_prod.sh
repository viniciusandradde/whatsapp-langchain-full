#!/usr/bin/env bash
#
# Backup diário do banco de produção. RODA NO VPS.
#
# Este arquivo existe porque o levantamento de 2026-07-31 descobriu que a
# produção não tinha backup nenhum: sem cron, sem timer do systemd, tabela
# `backup` do Dokploy vazia, nenhum dump em disco. 1,1 GB com o histórico de
# oito empresas e o WhatsApp de um cliente pagante, sem rede de proteção.
#
# Instalar (uma vez):
#   sudo scripts/backup_prod.sh --instalar
#
# Rodar na mão:
#   scripts/backup_prod.sh
#
# Restaurar (leia antes de precisar, não durante):
#   scripts/backup_prod.sh --restaurar /home/dev/backup/prod-AAAA-MM-DD.dump.$EXT
#
set -euo pipefail

CONTAINER_DB="${CONTAINER_DB:-projetos-chatvsanexus-er02mp-db-1}"
BANCO="${BANCO:-whatsapp_langchain}"
# `/home/dev/backup`, não `/var/backups`: fica no mesmo lugar do projeto,
# sobrevive a `dnf` mexendo em /var, e é gravável pelo `opc` — o timer roda
# como root, mas rodar na mão não deve exigir sudo.
DESTINO="${DESTINO:-/home/dev/backup}"
RETENCAO_DIAS="${RETENCAO_DIAS:-14}"
# MinIO já roda neste host (crm-minio). Espelhar ali dá versionamento sem
# infraestrutura nova — mas é a MESMA máquina. Ver "limitação" no fim.
MINIO_ALIAS="${MINIO_ALIAS:-}"
MINIO_BUCKET="${MINIO_BUCKET:-chatnexus-backups}"
# Cópia FORA do host, via rclone (Google Drive). Vazio = desligado. Foi o
# incidente de 2026-08-19 que provou a limitação descrita no fim deste arquivo:
# o servidor sumiu e levou disco e MinIO junto.
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
RCLONE_RETENCAO_DIAS="${RCLONE_RETENCAO_DIAS:-90}"
# Marcador do último upload bem-sucedido. É o que o relatório de produção lê
# (`producao_checks.checar_backup_offsite`) — sem ele, falha de upload some.
MARCADOR_OFFSITE="${MARCADOR_OFFSITE:-.ultimo_upload_offsite_ok}"
# O `sudo` usa a `secure_path` do sudoers, que NÃO inclui /usr/local/bin — é
# onde o rclone se instala. Sem esta busca, rodar o backup na mão com sudo
# alertaria "rclone não instalado" com o binário ali do lado, justamente no dia
# em que alguém roda na mão porque algo já deu errado.
RCLONE_BIN="${RCLONE_BIN:-}"
if [ -z "$RCLONE_BIN" ]; then
  if command -v rclone >/dev/null; then
    RCLONE_BIN="rclone"
  elif [ -x /usr/local/bin/rclone ]; then
    RCLONE_BIN="/usr/local/bin/rclone"
  fi
fi

# Compressor, em ordem de preferência. `zstd` comprime melhor e mais rápido;
# `pigz` usa todos os núcleos e é drop-in do gzip; `gzip` é o piso que sempre
# existe. A detecção em runtime evita que o script dependa de qual máquina o
# está rodando — o VPS e a máquina local não têm o mesmo conjunto.
if command -v zstd >/dev/null; then
  COMPRIMIR="zstd -T0 -3 -q -c"; DESCOMPRIMIR="zstd -dc"; EXT="zst"
elif command -v pigz >/dev/null; then
  COMPRIMIR="pigz -3 -c";        DESCOMPRIMIR="pigz -dc"; EXT="gz"
else
  COMPRIMIR="gzip -3 -c";        DESCOMPRIMIR="gzip -dc"; EXT="gz"
fi

log() { printf '%s  %s\n' "$(date -Is)" "$*"; }

# Alerta por Telegram, mesmo canal e mesmo arquivo de config do
# `monitor_evolution.sh`. WhatsApp não serve aqui: quando o host cai, é
# justamente o WhatsApp que para junto.
CONFIG_ALERTA="${CONFIG_ALERTA:-/etc/chatnexus-monitor.env}"
NL=$'\n'   # quebra de linha real: --data-urlencode escaparia um %0A literal
alerta() {
  local texto="$1"
  log "ALERTA: $texto"
  # shellcheck source=/dev/null
  [ -f "$CONFIG_ALERTA" ] && . "$CONFIG_ALERTA"
  if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    log "  (Telegram não configurado em $CONFIG_ALERTA — alerta só no log)"
    return 0
  fi
  curl -s -m 20 -o /dev/null \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${texto}" \
    --data-urlencode "parse_mode=HTML" \
    && log "  (enviado ao Telegram)"
  return 0
}

# --- Instalação do timer ---------------------------------------------------

if [ "${1:-}" = "--instalar" ]; then
  [ "$(id -u)" -eq 0 ] || { echo "precisa de sudo para instalar o timer" >&2; exit 1; }
  SCRIPT="$(readlink -f "$0")"

  cat > /etc/systemd/system/chatnexus-backup.service <<EOF
[Unit]
Description=Backup do banco Chat Nexus
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=$SCRIPT
# Backup não pode competir com o worker atendendo cliente.
Nice=10
IOSchedulingClass=idle
EOF

  cat > /etc/systemd/system/chatnexus-backup.timer <<'EOF'
[Unit]
Description=Backup diário do banco Chat Nexus

[Timer]
# 03:15 é o vale de tráfego — a fila mostrou zero mensagem entre 2h e 6h.
OnCalendar=*-*-* 03:15:00
# Se a máquina estava desligada na hora, roda ao ligar.
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now chatnexus-backup.timer
  log "timer instalado. Próxima execução:"
  systemctl list-timers chatnexus-backup.timer --no-pager | head -3
  log "Rode agora uma vez para validar:  $SCRIPT"
  exit 0
fi

# --- Restauração -----------------------------------------------------------
#
# Restaura numa base NOVA, nunca por cima da de produção. Trocar a produção
# pela restaurada é decisão humana, feita depois de conferir.

if [ "${1:-}" = "--restaurar" ]; then
  ARQ="${2:-}"
  [ -f "$ARQ" ] || { echo "uso: $0 --restaurar <arquivo.dump.$EXT>" >&2; exit 1; }
  ALVO="${3:-restaurado_$(date +%Y%m%d_%H%M)}"
  log "restaurando $ARQ em '$ALVO' (a produção NÃO é tocada)"
  docker exec "$CONTAINER_DB" psql -U postgres -q -c "CREATE DATABASE \"$ALVO\";"
  $DESCOMPRIMIR "$ARQ" | docker exec -i "$CONTAINER_DB" \
    pg_restore -U postgres -d "$ALVO" --no-owner --no-acl 2>&1 | tail -5 || true
  log "pronto. Confira com:"
  log "  docker exec $CONTAINER_DB psql -U postgres -d $ALVO -c 'select count(*) from cliente;'"
  log "Para descartar:  docker exec $CONTAINER_DB psql -U postgres -c 'DROP DATABASE \"$ALVO\";'"
  exit 0
fi

# --- Backup ----------------------------------------------------------------

mkdir -p "$DESTINO"
ARQUIVO="$DESTINO/prod-$(date +%F).dump.$EXT"

log "iniciando backup de $BANCO"
docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_DB" \
  || { log "ERRO: container $CONTAINER_DB não está rodando"; exit 1; }

# `-Fc` (custom) porque permite restauração seletiva de tabela e já vem
# comprimido; o pigz por cima ainda tira mais um pouco.
docker exec "$CONTAINER_DB" pg_dump -U postgres -Fc "$BANCO" \
  | $COMPRIMIR > "$ARQUIVO"

TAMANHO=$(du -h "$ARQUIVO" | cut -f1)
log "gravado: $ARQUIVO ($TAMANHO)"

# Um dump que não restaura não é backup.
#
# `pg_restore -l` lê o índice (TOC) e falha se o arquivo estiver truncado ou
# corrompido. Duas armadilhas, ambas descobertas testando:
#
#   1. NÃO funciona em pipe — o formato custom precisa de arquivo posicionável,
#      e `... | pg_restore -l` devolve "did not find magic string in file
#      header" mesmo num dump perfeito. Descomprime pra arquivo temporário.
#   2. `pg_restore` pode não existir no host (é o caso deste VPS, onde o
#      Postgres só vive no container). Por isso a verificação roda por dentro
#      do container quando não há binário local.
TMP_VERIF="$(mktemp "${TMPDIR:-/tmp}/verifica-backup-XXXXXX.dump")"
trap 'rm -f "$TMP_VERIF"' EXIT
$DESCOMPRIMIR "$ARQUIVO" > "$TMP_VERIF" 2>/dev/null

if command -v pg_restore >/dev/null; then
  VERIFICA=(pg_restore -l "$TMP_VERIF")
  ENTRADAS=$("${VERIFICA[@]}" 2>/dev/null | grep -c '^[0-9]' || true)
else
  docker cp "$TMP_VERIF" "$CONTAINER_DB:/tmp/verifica.dump" >/dev/null 2>&1
  ENTRADAS=$(docker exec "$CONTAINER_DB" pg_restore -l /tmp/verifica.dump 2>/dev/null \
             | grep -c '^[0-9]' || true)
  docker exec "$CONTAINER_DB" rm -f /tmp/verifica.dump >/dev/null 2>&1 || true
fi

# Um dump íntegro deste banco tem ~1.570 entradas. Menos de 100 significa
# arquivo truncado ou dump de banco vazio — nos dois casos, não serve.
if [ "${ENTRADAS:-0}" -ge 100 ]; then
  log "integridade conferida ($ENTRADAS objetos no índice)"
else
  log "ERRO: o dump tem só ${ENTRADAS:-0} objeto(s) — truncado ou corrompido."
  log "Apagando e falhando. NÃO existe backup válido de hoje."
  rm -f "$ARQUIVO"
  exit 1
fi

# --- Espelho no MinIO ------------------------------------------------------

if [ -n "$MINIO_ALIAS" ] && command -v mc >/dev/null; then
  if mc ls "$MINIO_ALIAS/$MINIO_BUCKET" >/dev/null 2>&1 \
     || mc mb "$MINIO_ALIAS/$MINIO_BUCKET" >/dev/null 2>&1; then
    mc cp "$ARQUIVO" "$MINIO_ALIAS/$MINIO_BUCKET/" >/dev/null \
      && log "espelhado no MinIO ($MINIO_ALIAS/$MINIO_BUCKET)"
  fi
else
  log "MinIO não configurado (defina MINIO_ALIAS) — só cópia local"
fi

# --- Cópia fora do host (rclone → Google Drive) ----------------------------
#
# Roda DEPOIS da verificação de integridade: só sobe o que já se provou
# restaurável. Falha aqui NÃO derruba o script — o backup local continua
# válido —, mas grita no Telegram na hora, porque backup offsite que para de
# funcionar em silêncio é a mesma armadilha do backup que nunca existiu.

if [ -n "$RCLONE_REMOTE" ]; then
  if [ -z "$RCLONE_BIN" ]; then
    alerta "<b>Chat Nexus — backup</b>${NL}RCLONE_REMOTE está configurado mas o rclone não está instalado. O backup de hoje NÃO foi copiado para fora do host."
  else
    NOME="$(basename "$ARQUIVO")"
    # A saída vai para variável, não para um pipe: `rclone ... | tail` devolve o
    # status do `tail` (sempre 0) e engoliria a falha do upload.
    SAIDA_RCLONE="$("$RCLONE_BIN" copyto "$ARQUIVO" "$RCLONE_REMOTE/$NOME" 2>&1)" \
      && COPIOU=1 || COPIOU=0
    [ -n "$SAIDA_RCLONE" ] && log "rclone: $(printf '%s' "$SAIDA_RCLONE" | tail -3 | tr '\n' ' ')"

    # `lsf` confirma que o arquivo ficou no destino. O exit 0 do copy sozinho
    # não basta: remoto que aceita e descarta depois existe.
    if [ "$COPIOU" = 1 ] && "$RCLONE_BIN" lsf "$RCLONE_REMOTE/$NOME" >/dev/null 2>&1; then
      log "enviado para fora do host ($RCLONE_REMOTE/$NOME)"
      touch "$DESTINO/$MARCADOR_OFFSITE"

      REMOVIDOS_REMOTO=$("$RCLONE_BIN" delete "$RCLONE_REMOTE" \
        --min-age "${RCLONE_RETENCAO_DIAS}d" --include "prod-*.dump.*" \
        -v 2>&1 | grep -c 'Deleted' || true)
      # `if` em vez de `[ ... ] && log`: com nada a remover (o caso normal), a
      # lista devolveria 1, o bloco `then` inteiro devolveria 1 e o `set -e`
      # abortaria o script ANTES da retenção local e do resumo final.
      if [ "${REMOVIDOS_REMOTO:-0}" -gt 0 ]; then
        log "removidos $REMOVIDOS_REMOTO backup(s) remotos com mais de $RCLONE_RETENCAO_DIAS dias"
      fi
    else
      alerta "<b>Chat Nexus — backup</b>${NL}Falhou o envio do backup para <code>$RCLONE_REMOTE</code>. O dump local de hoje está OK, mas não existe cópia fora do host."
    fi
  fi
else
  log "cópia externa não configurada (defina RCLONE_REMOTE) — backup só neste host"
fi

# --- Config cifrada: sessão do WhatsApp + env do Dokploy -------------------
#
# O dump acima cobre o banco da APP, mas não o que faz um servidor NOVO virar
# produção: a sessão Baileys (tabela `Session` da Evolution — perdê-la = re-
# parear todos os números) e as variáveis de ambiente (banco do Dokploy). Até
# 2026-09 isso só saía pelo `exportar_producao.sh` rodado NA MÃO e ficava
# semanas defasado. Agora vai junto no timer, CIFRADO (GPG): a sessão dá
# controle do WhatsApp e o env tem todas as chaves — não sobe em claro.
#
# Containers descobertos por filtro (o sufixo muda a cada redeploy). Best-effort:
# falha aqui alerta, mas NÃO invalida o backup do banco (que já subiu acima).

CONTAINER_EVO_PG="${CONTAINER_EVO_PG:-$(docker ps --filter name=evolution-postgres --format '{{.Names}}' | head -1)}"
CONTAINER_DOKPLOY_PG="${CONTAINER_DOKPLOY_PG:-$(docker ps --filter name=dokploy-postgres --format '{{.Names}}' | head -1)}"
GPG_PASS_FILE="${GPG_PASS_FILE:-/root/.config/chatnexus-backup.pass}"
RCLONE_REMOTE_CONFIG="${RCLONE_REMOTE_CONFIG:-}"

if [ -n "$RCLONE_REMOTE_CONFIG" ] && [ -n "$RCLONE_BIN" ] && command -v gpg >/dev/null; then
  CFG_TMP="$(mktemp -d "${TMPDIR:-/tmp}/chatnexus-config-XXXXXX")"
  CFG_OK=1
  if [ -n "$CONTAINER_EVO_PG" ]; then
    docker exec "$CONTAINER_EVO_PG" pg_dump -U evolution -Fc evolution > "$CFG_TMP/evolution.dump" 2>/dev/null
    [ -s "$CFG_TMP/evolution.dump" ] || { CFG_OK=0; log "AVISO: dump da Evolution (sessão) falhou"; }
  else
    CFG_OK=0; log "AVISO: container evolution-postgres não encontrado — sessão fora do backup"
  fi
  if [ -n "$CONTAINER_DOKPLOY_PG" ]; then
    docker exec "$CONTAINER_DOKPLOY_PG" pg_dump -U dokploy -Fc dokploy > "$CFG_TMP/dokploy.dump" 2>/dev/null \
      || log "AVISO: dump do Dokploy (env) falhou"
  fi
  # Passphrase estável; na 1ª vez gera e GRITA pro dono guardar FORA do host.
  if [ ! -f "$GPG_PASS_FILE" ]; then
    mkdir -p "$(dirname "$GPG_PASS_FILE")"
    ( umask 077; head -c 32 /dev/urandom | base64 > "$GPG_PASS_FILE" )
    alerta "<b>Chat Nexus — backup</b>${NL}Senha do backup de config gerada em <code>$GPG_PASS_FILE</code>. GUARDE-A FORA do servidor — sem ela o backup cifrado (sessão WhatsApp + env) no Drive não abre."
  fi
  if [ "$CFG_OK" = 1 ]; then
    CFG_PKG="$DESTINO/config-$(date +%F).tar.gz.gpg"
    if tar cz -C "$CFG_TMP" . \
         | gpg --batch --yes --symmetric --cipher-algo AES256 \
               --passphrase-file "$GPG_PASS_FILE" -o "$CFG_PKG" 2>/dev/null; then
      CFG_NOME="$(basename "$CFG_PKG")"
      if "$RCLONE_BIN" copyto "$CFG_PKG" "$RCLONE_REMOTE_CONFIG/$CFG_NOME" 2>/dev/null \
         && "$RCLONE_BIN" lsf "$RCLONE_REMOTE_CONFIG/$CFG_NOME" >/dev/null 2>&1; then
        log "config cifrada (sessão WhatsApp + env) enviada ($RCLONE_REMOTE_CONFIG/$CFG_NOME)"
        "$RCLONE_BIN" delete "$RCLONE_REMOTE_CONFIG" --min-age "${RCLONE_RETENCAO_DIAS}d" \
          --include "config-*.tar.gz.gpg" >/dev/null 2>&1 || true
      else
        alerta "<b>Chat Nexus — backup</b>${NL}Falhou o envio da config cifrada (sessão WhatsApp + env) para <code>$RCLONE_REMOTE_CONFIG</code>."
      fi
    fi
  fi
  rm -rf "$CFG_TMP"
else
  log "backup de config (sessão/env) desligado — precisa de RCLONE_REMOTE_CONFIG + gpg + rclone"
fi

# --- Mídia dos clientes (object storage, volume minio_data) ----------------
#
# Desde que o storage ligou (2026-09-15), a mídia do cliente vive SÓ no bucket
# — fora do pg_dump. Sem isto, migração/desastre perde fotos, áudios e docs.
# Objetos do MinIO são arquivos imutáveis, então tar do volume a quente é
# seguro (ao contrário de um pgdata a quente, que sai rasgado).

MINIO_VOLUME="${MINIO_VOLUME:-$(docker volume ls -q 2>/dev/null | grep '_minio_data$' | head -1)}"
if [ -n "$RCLONE_REMOTE" ] && [ -n "$RCLONE_BIN" ] && [ -n "$MINIO_VOLUME" ]; then
  MINIO_MP="$(docker volume inspect -f '{{.Mountpoint}}' "$MINIO_VOLUME" 2>/dev/null)"
  if [ -n "$MINIO_MP" ] && [ -d "$MINIO_MP" ]; then
    MINIO_ARQ="$DESTINO/minio-$(date +%F).tar.$EXT"
    if tar c -C "$MINIO_MP" . | $COMPRIMIR > "$MINIO_ARQ" 2>/dev/null && [ -s "$MINIO_ARQ" ]; then
      MINIO_NOME="$(basename "$MINIO_ARQ")"
      if "$RCLONE_BIN" copyto "$MINIO_ARQ" "$RCLONE_REMOTE/$MINIO_NOME" 2>/dev/null \
         && "$RCLONE_BIN" lsf "$RCLONE_REMOTE/$MINIO_NOME" >/dev/null 2>&1; then
        log "mídia (minio_data) enviada ($RCLONE_REMOTE/$MINIO_NOME, $(du -h "$MINIO_ARQ" | cut -f1))"
        "$RCLONE_BIN" delete "$RCLONE_REMOTE" --min-age "${RCLONE_RETENCAO_DIAS}d" \
          --include "minio-*.tar.*" >/dev/null 2>&1 || true
      else
        alerta "<b>Chat Nexus — backup</b>${NL}Falhou o envio da mídia (minio_data) para <code>$RCLONE_REMOTE</code>."
      fi
    fi
  fi
fi

# --- Retenção --------------------------------------------------------------

APAGADOS=$(find "$DESTINO" -name "prod-*.dump.$EXT" -mtime "+$RETENCAO_DIAS" -print -delete | wc -l)
[ "$APAGADOS" -gt 0 ] && log "removidos $APAGADOS backup(s) com mais de $RETENCAO_DIAS dias"
# Mídia e config cifrada seguem a mesma janela local.
find "$DESTINO" -name "minio-*.tar.$EXT"     -mtime "+$RETENCAO_DIAS" -delete 2>/dev/null || true
find "$DESTINO" -name "config-*.tar.gz.gpg"  -mtime "+$RETENCAO_DIAS" -delete 2>/dev/null || true

log "backups em disco: $(find "$DESTINO" -name "prod-*.dump.$EXT" | wc -l) ocupando $(du -sh "$DESTINO" | cut -f1)"

# ---------------------------------------------------------------------------
# COBERTURA
#
# Disco local e MinIO vivem NESTA máquina: protegem contra erro humano,
# migration ruim e `DROP TABLE` acidental. NÃO protegem contra perder o
# servidor — em 2026-08-19 o host sumiu e levou os dois junto.
#
# `RCLONE_REMOTE` fecha esse buraco: cópia fora do host, com retenção própria
# e alerta no Telegram quando o envio falha. Instalação SEM esse env continua
# com a limitação antiga — o backup é meia rede.
#
# Setup do remoto (uma vez, como root, pois o timer roda como root):
#   rclone authorize "drive" -- --scope drive.file   # numa máquina com navegador
#   rclone config                                    # colar o token no host
#   drop-in: Environment=RCLONE_REMOTE=gdrive:chatnexus-backups
#
# COBERTURA DIÁRIA (desde 2026-09-15) — este backup passou de "só o banco" a
# cobrir tudo que uma migração precisa, sem depender de rodar nada na mão:
#   - banco da app        → prod-DATA.dump.zst          (gdrive:chatnexus-backups)
#   - sessão WhatsApp+env  → config-DATA.tar.gz.gpg CIFRADO (RCLONE_REMOTE_CONFIG)
#   - mídia dos clientes   → minio-DATA.tar.zst          (gdrive:chatnexus-backups)
# Para ligar as duas partes novas, no drop-in do timer (e instalar `gpg` no host):
#   Environment=RCLONE_REMOTE_CONFIG=gdrive:chatnexus-config
# A senha do pacote cifrado nasce em GPG_PASS_FILE (default /root/.config/
# chatnexus-backup.pass) e DEVE ser guardada fora do host — sem ela o backup de
# sessão/env não abre. Restaurar: `exportar_producao.sh` documenta o caminho.
# ---------------------------------------------------------------------------
