#!/usr/bin/env bash
#
# Monitor da Evolution: detecta socket zumbi, tenta recuperar e avisa no Telegram.
#
# Existe por causa do incidente de 2026-07-31: as três instâncias ficaram ~13h
# sem receber mensagem enquanto `fetchInstances` respondia `open` alegremente. O
# estado é mentira — o socket do Baileys morre e o registro fica preso. Ninguém
# percebeu até um humano reclamar.
#
# O alerta vai por Telegram, e não por WhatsApp, de propósito: quando o WhatsApp
# é justamente o que quebrou, um aviso por WhatsApp não sai.
#
# Uso:
#   scripts/monitor_evolution.sh              # uma verificação
#   scripts/monitor_evolution.sh --instalar   # timer systemd de 5 em 5 minutos
#   scripts/monitor_evolution.sh --testar     # força um alerta, pra validar o Telegram
#
# Configuração em /etc/chatnexus-monitor.env:
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_CHAT_ID=...
#
set -uo pipefail   # sem -e de propósito: falha de sonda é dado, não motivo pra abortar

CONFIG="${CONFIG:-/etc/chatnexus-monitor.env}"
[ -f "$CONFIG" ] && . "$CONFIG"

EVOLUTION_URL="${EVOLUTION_URL:-https://evolutionapi.vsatecnologia.com.br}"
CONTAINER_EVO="${CONTAINER_EVO:-automao-evolutionapi-tp0jdo-evolution-api-1}"
CONTAINER_REDIS="${CONTAINER_REDIS:-automao-evolutionapi-tp0jdo-evolution-redis-1}"
CONTAINER_API="${CONTAINER_API:-projetos-chatvsanexus-er02mp-api-1}"

# Número usado como alvo da sonda. Só consultamos se ele existe no WhatsApp —
# nada é enviado. É o teste que exercita o socket sem virar spam de 5 em 5 min.
NUMERO_SONDA="${NUMERO_SONDA:-5567996460034}"

ESTADO_DIR="${ESTADO_DIR:-/var/lib/chatnexus-monitor}"
COOLDOWN_SEGUNDOS="${COOLDOWN_SEGUNDOS:-3600}"   # no máximo 1 restart por hora
ESPERA_RECONEXAO="${ESPERA_RECONEXAO:-120}"

mkdir -p "$ESTADO_DIR" 2>/dev/null

log() { printf '%s %s\n' "$(date -Is)" "$*"; }

NL=$'\n'   # quebra de linha real: --data-urlencode escaparia um %0A literal

# --- Telegram --------------------------------------------------------------

alerta() {
  local texto="$1"
  log "ALERTA: $texto"
  if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    log "  (Telegram não configurado em $CONFIG — alerta só no log)"
    return 1
  fi
  curl -s -m 20 -o /dev/null -w '' \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${texto}" \
    --data-urlencode "parse_mode=HTML" \
    && log "  (enviado ao Telegram)"
}

if [ "${1:-}" = "--testar" ]; then
  alerta "<b>Chat Nexus</b>${NL}Teste do monitor da Evolution. Se você recebeu isto, o alerta funciona."
  exit $?
fi

# --- Instalação do timer ---------------------------------------------------

if [ "${1:-}" = "--instalar" ]; then
  [ "$(id -u)" -eq 0 ] || { echo "rode com sudo" >&2; exit 1; }
  CAMINHO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  cat > /etc/systemd/system/chatnexus-monitor.service <<EOF
[Unit]
Description=Monitor da Evolution (socket zumbi) do Chat Nexus
After=docker.service

[Service]
Type=oneshot
ExecStart=$CAMINHO
EOF
  cat > /etc/systemd/system/chatnexus-monitor.timer <<'EOF'
[Unit]
Description=Verifica a Evolution de 5 em 5 minutos

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now chatnexus-monitor.timer
  echo "instalado — próximo disparo: $(systemctl show chatnexus-monitor.timer -p NextElapseUSecRealtime --value)"
  exit 0
fi

# --- Sonda -----------------------------------------------------------------

APIKEY="$(docker exec "$CONTAINER_API" printenv EVOLUTION_GLOBAL_API_KEY 2>/dev/null)"
if [ -z "$APIKEY" ]; then
  alerta "<b>Chat Nexus</b>${NL}Não consegui ler a chave da Evolution do container $CONTAINER_API. O monitor está cego."
  exit 1
fi

# Lista da própria Evolution. Não dá pra consultar o banco do Nexus: depois da
# migration 092 o `instance_name` mora DENTRO de `credentials_encrypted`, e não
# numa coluna — um `select instance_name` erra em silêncio e o monitor ficaria
# achando que não há nada para vigiar.
INSTANCIAS="$(curl -s -m 20 -H "apikey: $APIKEY" "$EVOLUTION_URL/instance/fetchInstances" 2>/dev/null \
  | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: raise SystemExit
if isinstance(d,dict): d=[d]
for i in d:
    n=i.get('instance',i)
    print(n.get('instanceName') or n.get('name') or '')
" 2>/dev/null)"

[ -z "$INSTANCIAS" ] && { alerta "<b>Chat Nexus</b>${NL}Não consegui listar as instâncias da Evolution."; exit 1; }

# O socket está vivo? `whatsappNumbers` percorre a conexão com o WhatsApp sem
# enviar nada. Socket morto responde erro ou "Connection Closed".
sonda_viva() {
  local inst="$1"
  local resp
  resp="$(curl -s -m 25 -X POST -H "apikey: $APIKEY" -H "Content-Type: application/json" \
    "$EVOLUTION_URL/chat/whatsappNumbers/$inst" \
    -d "{\"numbers\":[\"$NUMERO_SONDA\"]}" 2>/dev/null)"
  echo "$resp" | grep -q '"exists"'
}

MORTAS=()
for inst in $INSTANCIAS; do
  if sonda_viva "$inst"; then
    log "ok    $inst"
  else
    log "MORTA $inst"
    MORTAS+=("$inst")
  fi
done

[ "${#MORTAS[@]}" -eq 0 ] && { log "todas as instâncias respondem"; exit 0; }

# --- Recuperação -----------------------------------------------------------

LISTA="$(printf '%s, ' "${MORTAS[@]}")"; LISTA="${LISTA%, }"

# Guarda: sem as credenciais no Redis, reiniciar joga tudo em QR code. Nesse
# caso o certo é NÃO reiniciar e chamar um humano. As creds ficam num hash
# `evolution:instance:<uuid>`, campo `creds` — `get` devolve WRONGTYPE.
SEM_CREDS=0
for id in $(docker exec "$CONTAINER_REDIS" redis-cli --scan --pattern 'evolution:instance:*' 2>/dev/null | tr -d '\r'); do
  c="$(docker exec "$CONTAINER_REDIS" redis-cli hget "$id" creds 2>/dev/null)"
  [ -z "$c" ] && SEM_CREDS=$((SEM_CREDS+1))
done
if [ "$SEM_CREDS" -gt 0 ]; then
  alerta "<b>Chat Nexus — Evolution parada</b>${NL}Instâncias sem responder: $LISTA${NL}${NL}<b>NÃO reiniciei</b>: $SEM_CREDS instância(s) estão sem credencial no Redis, e o restart cairia em leitura de QR code. Precisa de você."
  exit 1
fi

# Trava anti-loop: um restart por hora. Se voltar a morrer dentro da janela, o
# problema é outro e insistir só piora.
MARCA="$ESTADO_DIR/ultimo_restart"
AGORA="$(date +%s)"
ULTIMO="$(cat "$MARCA" 2>/dev/null || echo 0)"
if [ $((AGORA - ULTIMO)) -lt "$COOLDOWN_SEGUNDOS" ]; then
  alerta "<b>Chat Nexus — Evolution parada de novo</b>${NL}Instâncias: $LISTA${NL}${NL}Não reiniciei: já houve restart há $(( (AGORA-ULTIMO)/60 ))min. Reiniciar em laço não resolveria. Precisa de você."
  exit 1
fi

log "recuperando: BGSAVE + restart de $CONTAINER_EVO"
docker exec "$CONTAINER_REDIS" redis-cli bgsave >/dev/null 2>&1
echo "$AGORA" > "$MARCA"
docker restart "$CONTAINER_EVO" >/dev/null 2>&1

# Espera reconectar antes de declarar vitória.
VIVAS=0
for _ in $(seq 1 $((ESPERA_RECONEXAO/10))); do
  sleep 10
  VIVAS=0
  for inst in "${MORTAS[@]}"; do sonda_viva "$inst" && VIVAS=$((VIVAS+1)); done
  [ "$VIVAS" -eq "${#MORTAS[@]}" ] && break
done

if [ "$VIVAS" -eq "${#MORTAS[@]}" ]; then
  alerta "<b>Chat Nexus — recuperado sozinho</b>${NL}A Evolution parou de responder (socket travado em 'open') e reiniciei o container.${NL}${NL}Instâncias afetadas: $LISTA${NL}Todas voltaram, sem precisar ler QR code.${NL}${NL}Não precisa fazer nada — é só pra você saber."
else
  alerta "<b>Chat Nexus — RECUPERAÇÃO FALHOU</b>${NL}Instâncias sem responder: $LISTA${NL}Reiniciei o container e $VIVAS de ${#MORTAS[@]} voltaram.${NL}${NL}<b>Precisa de você.</b> Verifique se alguma está pedindo QR code no painel."
  exit 1
fi
