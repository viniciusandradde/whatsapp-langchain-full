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
#   scripts/backup_prod.sh --restaurar /var/backups/chatnexus/prod-AAAA-MM-DD.dump.$EXT
#
set -euo pipefail

CONTAINER_DB="${CONTAINER_DB:-projetos-chatvsanexus-er02mp-db-1}"
BANCO="${BANCO:-whatsapp_langchain}"
DESTINO="${DESTINO:-/var/backups/chatnexus}"
RETENCAO_DIAS="${RETENCAO_DIAS:-14}"
# MinIO já roda neste host (crm-minio). Espelhar ali dá versionamento sem
# infraestrutura nova — mas é a MESMA máquina. Ver "limitação" no fim.
MINIO_ALIAS="${MINIO_ALIAS:-}"
MINIO_BUCKET="${MINIO_BUCKET:-chatnexus-backups}"

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

# Um dump que não restaura não é backup. `pg_restore -l` lê o índice do
# arquivo e falha se ele estiver truncado ou corrompido — barato o bastante
# pra rodar todo dia.
if $DESCOMPRIMIR "$ARQUIVO" | pg_restore -l >/dev/null 2>&1; then
  log "integridade conferida (índice legível)"
else
  log "ERRO: o dump não é legível. Apagando e falhando."
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

# --- Retenção --------------------------------------------------------------

APAGADOS=$(find "$DESTINO" -name "prod-*.dump.$EXT" -mtime "+$RETENCAO_DIAS" -print -delete | wc -l)
[ "$APAGADOS" -gt 0 ] && log "removidos $APAGADOS backup(s) com mais de $RETENCAO_DIAS dias"

log "backups em disco: $(find "$DESTINO" -name "prod-*.dump.$EXT" | wc -l) ocupando $(du -sh "$DESTINO" | cut -f1)"

# ---------------------------------------------------------------------------
# LIMITAÇÃO CONHECIDA
#
# Tudo aqui — disco e MinIO — vive NESTA máquina. Isso protege contra erro
# humano, migration ruim e `DROP TABLE` acidental, que são as causas prováveis.
# NÃO protege contra perder o servidor: incêndio, disco morto, conta suspensa.
#
# Fechar isso precisa de destino externo (S3, Backblaze, outra VPS) e é
# decisão de custo. Enquanto não existir, este backup é meia rede.
# ---------------------------------------------------------------------------
