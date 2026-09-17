#!/usr/bin/env bash
# Espelho diário COMPLETO de produção na VPS local (18h, via Tailscale).
#
# Nasceu da emergência de 2026-09-17 (a máquina da OCI podia ser desligada):
# é a mesma sequência feita à mão naquela noite, agora todo dia. Complementa —
# não substitui — o `backup_prod.sh` do host (03:15, banco da app → Google
# Drive) e o pull das 04:30 (`~/backups/chatnexus-prod`). Aqui entra o que
# esses dois não cobrem: sessões WhatsApp, envs do Dokploy, configs do host e
# TODOS os volumes Docker (inclusive os de outros projetos parados no host).
#
# Roda na VPS local e puxa do host por SSH:
#
#   ./scripts/backup_espelho_vps.sh          # snapshot de agora
#   RETENCAO_DIAS=30 ./scripts/backup_espelho_vps.sh
#
# Notifica no WhatsApp do dono (Evolution) e, se a Evolution não responder —
# que é exatamente o caso da OCI fora do ar — cai pro Telegram do monitor.
# Segredos em ~/.config/chatnexus-espelho.env (WA_DESTINO, WA_INSTANCIA,
# EVOLUTION_URL, EVOLUTION_APIKEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).
#
# Layout (um diretório por execução, volumes deduplicados por hardlink):
#
#   ~/backups/chatnexus-espelho/
#     2026-09-18_1800/
#       export/     exportar_producao.sh (dump NOVO da app, Evolution, Dokploy,
#                   envs, configs, manifesto) — verificado em base descartável
#       volumes/    /var/lib/docker/volumes do host (rsync --link-dest)
#       host/       /home/opc, /etc/dokploy, env de TODOS os containers
#       RELATORIO.txt
#     ultimo -> 2026-09-18_1800
#     log/espelho-2026-09-18.log
#     .ultimo_ok  (mtime = última execução íntegra; é o que se monitora)
#
# Volumes de Postgres copiados a quente (postgres_data, evolution_pgdata,
# dokploy-postgres) são só ÚLTIMA ESPERANÇA — restaurar é pelos dumps do
# export. Ver docs/MIGRACAO_SERVIDOR.md.

set -uo pipefail

HOST="${HOST:-opc@100.116.235.14}"
RAIZ="${RAIZ:-$HOME/backups/chatnexus-espelho}"
RETENCAO_DIAS="${RETENCAO_DIAS:-14}"
CONFIG_NOTIFICA="${CONFIG_NOTIFICA:-$HOME/.config/chatnexus-espelho.env}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

TS="$(date +%Y-%m-%d_%H%M)"
DEST="$RAIZ/$TS"
LOG="$RAIZ/log/espelho-$(date +%F).log"
mkdir -p "$DEST"/{volumes,host/envs} "$RAIZ/log"

exec > >(tee -a "$LOG") 2>&1
log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
erro() { printf '[%s] ERRO: %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
NL=$'\n'

# ------------------------------------------------------------- notificar ----
# WhatsApp pela Evolution primeiro; Telegram só se a Evolution não confirmar.
# Nunca derruba o backup: notificação é best-effort.
notificar() {
  local texto="$1"
  # shellcheck source=/dev/null
  [ -f "$CONFIG_NOTIFICA" ] && . "$CONFIG_NOTIFICA"
  if [ -n "${EVOLUTION_URL:-}" ] && [ -n "${EVOLUTION_APIKEY:-}" ] \
     && [ -n "${WA_INSTANCIA:-}" ] && [ -n "${WA_DESTINO:-}" ]; then
    local payload resp
    payload=$(python3 -c 'import json,sys; print(json.dumps({"number": sys.argv[1], "text": sys.argv[2]}))' \
              "$WA_DESTINO" "$texto")
    resp=$(curl -s -m 25 -X POST -H "apikey: $EVOLUTION_APIKEY" -H "Content-Type: application/json" \
             "$EVOLUTION_URL/message/sendText/$WA_INSTANCIA" -d "$payload" 2>/dev/null)
    if printf '%s' "$resp" | grep -q '"status":"PENDING"\|"status":"SERVER_ACK"\|"status":"DELIVERY_ACK"'; then
      log "  (notificado no WhatsApp $WA_DESTINO)"; return 0
    fi
    log "  (WhatsApp não confirmou: ${resp:0:120})"
  fi
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -s -m 20 -o /dev/null "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${texto}" \
      && log "  (notificado no Telegram)" && return 0
  fi
  log "  (nenhum canal de notificação respondeu — só no log)"
  return 0
}

# Uma execução por vez: o rsync de ontem ainda rodando não pode encavalar com
# o de hoje (o --link-dest apontaria pra um snapshot incompleto).
exec 9>"$RAIZ/.lock"
if ! flock -n 9; then
  erro "outra execução em andamento (lock $RAIZ/.lock) — abortando"
  notificar "⚠️ Espelho Chat Nexus $TS NÃO rodou: execução anterior ainda em andamento."
  exit 3
fi

log "==== espelho $TS → $DEST"
FALHAS=0
AVISOS=()

if ! ssh -o ConnectTimeout=20 -o BatchMode=yes "$HOST" true 2>/dev/null; then
  erro "host $HOST inacessível por SSH"
  notificar "🚨 Espelho Chat Nexus $TS FALHOU: host $HOST inacessível por SSH (Tailscale?). Nada foi copiado."
  exit 2
fi

# ------------------------------------------------------------ 1. export ----
# Dump NOVO da app + Evolution + Dokploy + envs + configs. `DESTINO` faz o
# export cair dentro do snapshot; o script cria um subdir com timestamp
# próprio, que é movido pra `export/` pra ficar previsível.
log "1/5 export consistente (exportar_producao.sh, DUMP_NOVO=1)"
EXPORT_DIR=$(DUMP_NOVO=1 DESTINO="$DEST/.export-tmp" HOST="$HOST" \
      "$REPO/scripts/exportar_producao.sh" 2>&1 | tee /dev/stderr | tail -1)
if [ -d "$EXPORT_DIR" ]; then
  mv "$EXPORT_DIR" "$DEST/export" && rmdir "$DEST/.export-tmp" 2>/dev/null
  log "export ok — $(du -sh "$DEST/export" | cut -f1)"
else
  erro "export falhou"; FALHAS=$((FALHAS+1))
fi

# -------------------------------------------------------- 2. verificação ----
# Restaura cada dump em Postgres descartável e confere sessões/envs. Tamanho
# de arquivo não prova nada: dump truncado também tem tamanho.
if [ -d "$DEST/export" ]; then
  log "2/5 verificação do export"
  if "$REPO/scripts/exportar_producao.sh" --verificar "$DEST/export"; then
    log "verificação ok"
  else
    erro "verificação FALHOU — o snapshot pode não restaurar"; FALHAS=$((FALHAS+1))
  fi
else
  log "2/5 verificação pulada (sem export)"
fi

# ------------------------------------------------------------ 3. volumes ----
# --link-dest: arquivo igual ao do snapshot anterior vira hardlink (zero bytes
# a mais). Só o que mudou custa disco e rede.
log "3/5 rsync dos volumes Docker, /home/opc e /etc/dokploy"
ULTIMO=""
[ -L "$RAIZ/ultimo" ] && ULTIMO="$(readlink -f "$RAIZ/ultimo")"
LINK=()
[ -n "$ULTIMO" ] && [ -d "$ULTIMO/volumes" ] && LINK=(--link-dest="$ULTIMO/volumes")
if rsync -a --delete --timeout=300 --rsync-path="sudo rsync" "${LINK[@]}" \
     "$HOST:/var/lib/docker/volumes/" "$DEST/volumes/"; then
  log "volumes ok — $(du -sh "$DEST/volumes" | cut -f1) aparentes"
else
  erro "rsync dos volumes falhou"; FALHAS=$((FALHAS+1))
fi

LINK=()
[ -n "$ULTIMO" ] && [ -d "$ULTIMO/host" ] && LINK=(--link-dest="$ULTIMO/host")
rsync -a --delete --timeout=300 --rsync-path="sudo rsync" "${LINK[@]}" \
  "$HOST:/home/opc/" "$DEST/host/home-opc/" || { erro "rsync /home/opc falhou"; FALHAS=$((FALHAS+1)); }
rsync -a --delete --timeout=300 --rsync-path="sudo rsync" \
  "$HOST:/etc/dokploy/" "$DEST/host/etc-dokploy/" || { erro "rsync /etc/dokploy falhou"; FALHAS=$((FALHAS+1)); }

# Env de TODOS os containers em execução (o export cobre só os 6 do Nexus;
# Dokploy, Traefik, registry, MinIO etc. também têm config só no `inspect`).
ssh "$HOST" 'for c in $(sudo docker ps --format "{{.Names}}"); do echo "### $c"; sudo docker inspect "$c" --format "{{range .Config.Env}}{{println .}}{{end}}"; done' \
  > "$DEST/host/envs/todos-os-containers.txt" 2>/dev/null || AVISOS+=("env dos containers não capturado")
chmod 600 "$DEST/host/envs/todos-os-containers.txt" 2>/dev/null

# --------------------------------------------------------- 4. revalidação ----
# "Ficou algo sem backup?" — confere contra o host, não contra o que o script
# acha que copiou.
log "4/5 revalidação contra o host"
VOL_HOST=$(ssh "$HOST" 'sudo docker volume ls -q' 2>/dev/null | sort)
VOL_LOCAL=$(ls -1 "$DEST/volumes" 2>/dev/null | sort)
FALTANDO=$(comm -23 <(echo "$VOL_HOST") <(echo "$VOL_LOCAL"))
N_VOL_HOST=$(echo "$VOL_HOST" | grep -c .)
if [ -n "$FALTANDO" ]; then
  erro "volumes do host SEM cópia: $(echo "$FALTANDO" | tr '\n' ' ')"; FALHAS=$((FALHAS+1))
else
  log "volumes: $N_VOL_HOST no host, $N_VOL_HOST copiados"
fi

# 2ª passada: o que a 1ª deixou passar por corrida com escrita (mídia chegando
# no MinIO no meio da cópia). Volumes de banco mudam sempre — não contam.
PASSA2=$(rsync -ai --delete --timeout=300 --rsync-path="sudo rsync" \
           --exclude='*postgres*' --exclude='*pgdata*' --exclude='*redis*' \
           "$HOST:/var/lib/docker/volumes/" "$DEST/volumes/" 2>/dev/null | grep -c '^[<>]f' || true)
if [ "${PASSA2:-0}" -gt 0 ]; then
  log "2ª passada trouxe $PASSA2 arquivo(s) que mudaram durante a 1ª (agora copiados)"
else
  log "2ª passada: nada mudou durante a cópia"
fi

CT_HOST=$(ssh "$HOST" 'sudo docker ps --format "{{.Names}}"' 2>/dev/null | sort)
N_CT=$(echo "$CT_HOST" | grep -c .)
N_ENV=$(grep -c '^### ' "$DEST/host/envs/todos-os-containers.txt" 2>/dev/null || echo 0)
[ "$N_ENV" -eq "$N_CT" ] && log "containers: $N_CT rodando, $N_ENV com env capturado" \
  || { AVISOS+=("env: $N_ENV de $N_CT containers"); }

for d in whatsapp_langchain.dump.zst evolution.dump dokploy.dump; do
  [ -s "$DEST/export/dados/$d" ] || { erro "dump ausente ou vazio: $d"; FALHAS=$((FALHAS+1)); }
done
for f in etc-dokploy.tar.gz systemd-chatnexus.tar.gz; do
  [ -s "$DEST/export/config/$f" ] || AVISOS+=("config ausente: $f")
done
[ -s "$DEST/export/segredos/rclone.conf" ] || AVISOS+=("rclone.conf ausente")

# ---------------------------------------------------------- 5. fechamento ----
log "5/5 relatório, ponteiro e retenção"
TAM_EXPORT=$([ -d "$DEST/export" ] && du -sh "$DEST/export" | cut -f1 || echo AUSENTE)
TAM_VOL=$(du -sh "$DEST/volumes" | cut -f1)
LIVRE=$(df -h "$RAIZ" | awk 'NR==2{print $4}')
{
  echo "espelho: $TS"
  echo "host: $HOST"
  echo "falhas: $FALHAS"
  echo "avisos: ${AVISOS[*]:-nenhum}"
  echo "export: $TAM_EXPORT"
  echo "volumes: $TAM_VOL ($N_VOL_HOST volumes)"
  echo "containers rodando: $N_CT (env capturado: $N_ENV)"
  echo "disco livre: $LIVRE"
  echo "volumes (do host):"
  echo "$VOL_LOCAL" | sed 's/^/  /'
} > "$DEST/RELATORIO.txt"

if [ "$FALHAS" -eq 0 ]; then
  ln -sfn "$TS" "$RAIZ/ultimo"
  touch "$RAIZ/.ultimo_ok"
  # Retenção só apaga quando a execução de hoje ficou íntegra: um dia ruim não
  # pode consumir os bons.
  find "$RAIZ" -maxdepth 1 -type d -name '20*' -mtime +"$RETENCAO_DIAS" \
    ! -path "$DEST" -exec rm -rf {} + 2>/dev/null
  find "$RAIZ/log" -name 'espelho-*.log' -mtime +90 -delete 2>/dev/null
  log "==== OK — $DEST"
  notificar "✅ Espelho Chat Nexus $TS OK${NL}export $TAM_EXPORT (verificado: sessões WhatsApp + envs restauram)${NL}volumes $TAM_VOL ($N_VOL_HOST/$N_VOL_HOST)${NL}containers $N_CT (env $N_ENV)${NL}avisos: ${AVISOS[*]:-nenhum}${NL}disco livre na VPS: $LIVRE"
  exit 0
fi

erro "==== TERMINOU COM $FALHAS FALHA(S) — snapshot $DEST mantido para inspeção; 'ultimo' NÃO avançou"
notificar "🚨 Espelho Chat Nexus $TS FALHOU ($FALHAS falha(s))${NL}$(grep 'ERRO:' "$LOG" | tail -5 | cut -c1-160)${NL}log: $LOG"
exit 1
