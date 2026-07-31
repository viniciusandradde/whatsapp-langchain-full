#!/usr/bin/env bash
#
# Recebe o pacote e levanta o ambiente de desenvolvimento. RODA NA SUA MÁQUINA.
#
# Uso:
#   scripts/migrar-dev/02-importar.sh vps-docker03:/tmp/chatnexus-migracao
#   scripts/migrar-dev/02-importar.sh /media/pendrive/chatnexus-migracao
#
# O contrato de isolamento (docs/MIGRACAO_DEV.md) é verificado aqui. Se
# qualquer trava faltar, o script para antes de subir o worker — porque um
# worker de desenvolvimento com credencial de produção manda WhatsApp de
# verdade pra pessoa de verdade.
#
set -euo pipefail

ORIGEM="${1:-}"
DESTINO="${DESTINO:-$HOME/projetos/chatnexus}"
TRABALHO="${TRABALHO:-/tmp/chatnexus-migracao-recebido}"
PROJETO_DOCKER="chatnexus-dev"

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

azul()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
verde() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
aviso() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
erro()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*" >&2; }

[ -z "$ORIGEM" ] && { erro "informe a origem: $0 vps-docker03:/tmp/chatnexus-migracao"; exit 1; }

for cmd in docker rsync tar uv node; do
  command -v "$cmd" >/dev/null || { erro "'$cmd' não encontrado — rode 01-preparar-maquina.sh"; exit 1; }
done
docker compose version >/dev/null 2>&1 || { erro "falta o plugin 'docker compose' v2"; exit 1; }

azul "Importando de $ORIGEM"
echo

# --- 1. Transferir ---------------------------------------------------------

azul "1/8  Baixando o pacote"
mkdir -p "$TRABALHO"
# `--partial --progress`: 2 GB numa conexão que pode cair; retomar é melhor
# que recomeçar.
rsync -avh --partial --progress "$ORIGEM/" "$TRABALHO/"
verde "recebido em $TRABALHO"

# --- 2. Conferir integridade ----------------------------------------------

azul "2/8  Conferindo sha256 do manifesto"
[ -f "$TRABALHO/MANIFESTO.txt" ] || { erro "MANIFESTO.txt não veio junto."; exit 1; }
FALHOU=0
while read -r arquivo _ hash; do
  [ -f "$TRABALHO/$arquivo" ] || continue
  atual=$(sha256sum "$TRABALHO/$arquivo" | cut -d' ' -f1)
  if [ "$atual" != "$hash" ]; then
    erro "$arquivo: sha256 não bate — transferência corrompida"
    FALHOU=1
  else
    verde "$arquivo"
  fi
done < <(grep -E '\.(dump|tar\.[a-z]+)\s' "$TRABALHO/MANIFESTO.txt")
[ "$FALHOU" -eq 1 ] && exit 1

# --- 3. Repositório --------------------------------------------------------

azul "3/8  Extraindo o repositório em $DESTINO"
if [ -d "$DESTINO/.git" ]; then
  aviso "$DESTINO já existe e tem git."
  read -rp "  Sobrescrever? Trabalho não commitado será PERDIDO. [s/N] " r
  [ "$r" = "s" ] || { erro "abortado."; exit 1; }
fi
mkdir -p "$DESTINO"
$DESCOMPRIMIR "$TRABALHO/repo.tar.$EXT" | tar -C "$DESTINO" -xf -
verde "branch $(git -C "$DESTINO" rev-parse --abbrev-ref HEAD) em $(git -C "$DESTINO" rev-parse --short HEAD)"

# --- 4. Estado do Claude ---------------------------------------------------

azul "4/8  Restaurando histórico e memória do Claude"
if [ -f "$TRABALHO/claude.tar.$EXT" ]; then
  mkdir -p "$HOME/.claude"
  if [ -d "$HOME/.claude/projects/-home-dev-projetos-chatnexus" ]; then
    aviso "já existe histórico deste projeto — preservando em .bak"
    mv "$HOME/.claude/projects/-home-dev-projetos-chatnexus" \
       "$HOME/.claude/projects/-home-dev-projetos-chatnexus.bak.$(date +%s)"
  fi
  $DESCOMPRIMIR "$TRABALHO/claude.tar.$EXT" | tar -C "$HOME/.claude" -xf -
  verde "histórico, memórias e planos restaurados"
  # O caminho do projeto vira a chave do diretório. Se o destino não for o
  # mesmo caminho do VPS, o Claude não acha o histórico.
  if [ "$DESTINO" != "/home/dev/projetos/chatnexus" ]; then
    aviso "o histórico está indexado por /home/dev/projetos/chatnexus,"
    aviso "mas você instalou em $DESTINO — renomeie o diretório em"
    aviso "~/.claude/projects/ para o padrão do novo caminho se quiser que"
    aviso "o Claude reencontre a conversa."
  fi
else
  aviso "claude.tar.$EXT não veio — seguindo sem histórico"
fi

# --- 5. Segredos com as travas do contrato ---------------------------------
#
# Esta é a seção que impede o acidente. O `.env` de produção vira `.env` de
# desenvolvimento com seis valores forçados, e cada um é conferido depois.

azul "5/8  Gerando .env de desenvolvimento"
if [ -f "$TRABALHO/segredos.tar.$EXT" ]; then
  $DESCOMPRIMIR "$TRABALHO/segredos.tar.$EXT" | tar -C "$DESTINO" -xf -
  verde "segredos de produção extraídos"
else
  erro "segredos.tar.$EXT não veio — sem ele o ambiente não sobe."
  exit 1
fi

python3 - "$DESTINO/.env" <<'PY'
import sys, pathlib

# As seis travas do contrato de isolamento. Chave → valor obrigatório.
TRAVAS = {
    "ENVIRONMENT":              "development",
    # A trava que mais importa: nada sai pra telefone real.
    "EVOLUTION_OUTBOUND_MODE":  "mock",
    "TWILIO_OUTBOUND_MODE":     "mock",
    # Banco local, porta do override. Nunca o de produção.
    "DATABASE_URL":             "postgresql://postgres:postgres@localhost:5434/whatsapp_langchain",
    "DATABASE_URL_APP":         "",
    # Traces de teste não entram no painel de produção.
    "LANGFUSE_ENABLED":         "false",
    # Assinatura do Twilio: em dev não há webhook real chegando.
    "VALIDATE_TWILIO_SIGNATURE": "false",
    # Endereços locais.
    "INTERNAL_API_URL":         "http://localhost:8081",
    "BETTER_AUTH_URL":          "http://localhost:3081",
    "FRONTEND_ORIGINS":         "http://localhost:3081,http://localhost:3000",
    # Segredos próprios: os de produção não devem valer aqui.
    "INTERNAL_SERVICE_TOKEN":   "dev-token-change-in-production",
    "BETTER_AUTH_SECRET":       "dev-secret-change-in-production-min-32-chars!!",
    # A chave do OpenRouter é a mesma e gasta de verdade — segura o ritmo.
    "LLM_RATE_LIMIT_REQUESTS_PER_SECOND": "1",
}

caminho = pathlib.Path(sys.argv[1])
linhas = caminho.read_text().splitlines()
vistas = set()
saida = []

for linha in linhas:
    if "=" in linha and not linha.lstrip().startswith("#"):
        chave = linha.split("=", 1)[0].strip()
        if chave in TRAVAS:
            saida.append(f"{chave}={TRAVAS[chave]}")
            vistas.add(chave)
            continue
    saida.append(linha)

faltando = [k for k in TRAVAS if k not in vistas]
if faltando:
    saida.append("")
    saida.append("# --- travas do ambiente de desenvolvimento ---")
    saida.extend(f"{k}={TRAVAS[k]}" for k in faltando)

caminho.write_text("\n".join(saida) + "\n")
print(f"  {len(TRAVAS)} travas aplicadas ({len(faltando)} acrescentadas)")
PY

# Front tem env próprio pro `npm run dev`.
cat > "$DESTINO/frontend/.env.local" <<'EOF'
# Desenvolvimento local. A API roda no compose, porta 8081.
INTERNAL_API_URL=http://localhost:8081
INTERNAL_SERVICE_TOKEN=dev-token-change-in-production
DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain
BETTER_AUTH_SECRET=dev-secret-change-in-production-min-32-chars!!
BETTER_AUTH_URL=http://localhost:3000
EOF
verde "frontend/.env.local"

# --- 6. Verificar o contrato ANTES de subir qualquer coisa -----------------

azul "6/8  Verificando o contrato de isolamento"
cd "$DESTINO"
PROBLEMAS=0
checar() {
  if grep -qE "^$1=$2\$" .env; then verde "$3"
  else erro "$3 — FALHOU"; PROBLEMAS=$((PROBLEMAS+1)); fi
}
checar EVOLUTION_OUTBOUND_MODE mock  "Evolution em mock (não manda WhatsApp)"
checar TWILIO_OUTBOUND_MODE    mock  "Twilio em mock"
checar LANGFUSE_ENABLED        false "Langfuse desligado"
checar ENVIRONMENT      development  "ENVIRONMENT=development"

if grep -qE '^DATABASE_URL=.*(vsanexus|100\.67\.148\.26|@db:)' .env; then
  erro "DATABASE_URL aponta pra fora da máquina — FALHOU"
  PROBLEMAS=$((PROBLEMAS+1))
else
  verde "DATABASE_URL é local"
fi

if [ "$PROBLEMAS" -gt 0 ]; then
  erro "$PROBLEMAS trava(s) do contrato falharam. Nada foi levantado."
  erro "Corrija $DESTINO/.env e rode de novo."
  exit 1
fi

# --- 7. Subir o stack ------------------------------------------------------
#
# `-p chatnexus-dev` dá nome de projeto próprio → volumes e rede isolados.
# As imagens do VPS são aarch64 e não servem aqui: `--build` recompila.

azul "7/8  Subindo o stack (primeira build leva alguns minutos)"
docker compose -p "$PROJETO_DOCKER" \
  -f docker-compose.yml -f docker-compose.override.yml \
  up -d --build db api worker

echo -n "  aguardando o banco"
for _ in $(seq 1 60); do
  if docker compose -p "$PROJETO_DOCKER" exec -T db pg_isready -U postgres >/dev/null 2>&1; then
    echo; verde "banco de pé na porta 5434"; break
  fi
  echo -n "."; sleep 2
done

azul "     Restaurando o banco de desenvolvimento"
# `pg_restore` do host é opcional: nem toda máquina tem postgresql-client, e
# o container tem o mesmo binário na versão certa. `--clean --if-exists`
# porque a API já criou schema no boot e o dump é quem manda.
if command -v pg_restore >/dev/null; then
  pg_restore -d postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    --no-owner --no-acl --clean --if-exists "$TRABALHO/dev.dump" 2>&1 \
    | grep -vE 'does not exist|already exists' || true
else
  aviso "pg_restore não existe no host — usando o do container"
  docker compose -p "$PROJETO_DOCKER" exec -T db \
    pg_restore -U postgres -d whatsapp_langchain \
    --no-owner --no-acl --clean --if-exists < "$TRABALHO/dev.dump" 2>&1 \
    | grep -vE 'does not exist|already exists' || true
fi
verde "dev.dump restaurado"

# --- 8. Dependências e verificação final -----------------------------------

azul "8/8  Instalando dependências"
uv venv --clear >/dev/null 2>&1
uv pip install -e ".[dev]" >/dev/null 2>&1
verde "Python (.venv)"
(cd frontend && npm ci --silent) && verde "Node (frontend/node_modules)"

# psql do host quando existe; senão o do container. Mesma resposta.
consultar() {
  if command -v psql >/dev/null; then
    psql postgresql://postgres:postgres@localhost:5434/whatsapp_langchain -At -c "$1" 2>/dev/null || echo 999
  else
    docker compose -p "$PROJETO_DOCKER" exec -T db \
      psql -U postgres -d whatsapp_langchain -At -c "$1" 2>/dev/null | tr -d '\r' || echo 999
  fi
}

echo
azul "Verificação final"
MIGS=$(consultar "select count(*) from _migrations;")
verde "$MIGS migrations aplicadas"

VAZOU=$(consultar "
  select (select count(*) from cliente where telefone not like '55119%')
       + (select count(*) from checkpoints)
       + (select count(*) from conexao where credentials_encrypted is not null);")
if [ "$VAZOU" = "0" ]; then
  verde "banco sem PII: nenhum telefone real, checkpoint ou credencial"
else
  erro "banco tem $VAZOU registro(s) suspeito(s) — investigue antes de usar"
fi

curl -sf http://localhost:8081/health >/dev/null \
  && verde "API respondendo em http://localhost:8081" \
  || aviso "API ainda não respondeu — veja: docker compose -p $PROJETO_DOCKER logs api"

echo
azul "Pronto. Ambiente de desenvolvimento no ar."
cat <<EOF

  API        http://localhost:8081
  Banco      postgresql://postgres:postgres@localhost:5434/whatsapp_langchain
  Frontend   cd frontend && npm run dev     (http://localhost:3000)

  Logs       docker compose -p $PROJETO_DOCKER logs -f
  Parar      docker compose -p $PROJETO_DOCKER down
  Testes     uv run pytest -m "not docker_demo and not twilio_real"

  A produção do Luis continua no VPS, intocada. Este ambiente está em mock:
  nada que você fizer aqui manda mensagem pra telefone real.
EOF
