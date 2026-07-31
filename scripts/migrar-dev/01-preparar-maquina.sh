#!/usr/bin/env bash
#
# Prepara a máquina Ubuntu/Debian para receber o ambiente. RODA NA SUA MÁQUINA.
#
# Idempotente: rode quantas vezes quiser. Só instala o que falta.
#
# Não usa o `docker.io` do apt de propósito — ele costuma vir várias versões
# atrás e sem o plugin `compose` v2, que este projeto exige (`docker compose`,
# não `docker-compose`).
#
set -euo pipefail

azul()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
verde() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
aviso() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
erro()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] && { erro "não rode como root — o script chama sudo onde precisa."; exit 1; }

command -v apt-get >/dev/null || { erro "este script é para Ubuntu/Debian."; exit 1; }

azul "Preparando $(. /etc/os-release && echo "$PRETTY_NAME") — $(uname -m)"
echo

# --- Básico ----------------------------------------------------------------

azul "1/6  Pacotes básicos"
sudo apt-get update -qq
sudo apt-get install -y -qq \
  git rsync curl ca-certificates gnupg pigz jq make build-essential
verde "git, rsync, curl, pigz, jq, make"

# --- Docker ----------------------------------------------------------------

azul "2/6  Docker Engine + compose v2"
if docker compose version >/dev/null 2>&1; then
  verde "já instalado ($(docker --version | cut -d, -f1))"
else
  sudo install -m 0755 -d /etc/apt/keyrings
  . /etc/os-release
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  verde "instalado ($(docker --version | cut -d, -f1))"
fi

if ! groups | grep -qw docker; then
  sudo usermod -aG docker "$USER"
  aviso "você foi adicionado ao grupo 'docker' — SAIA E ENTRE de novo na sessão"
  aviso "antes de rodar o 02-importar.sh, senão o docker vai pedir sudo."
fi

# --- Postgres client -------------------------------------------------------
#
# Precisa ser >= 16: o `pg_restore` recusa dump gerado por servidor mais novo
# que ele, e o banco de produção é o 16.

azul "3/6  Cliente PostgreSQL 16"
if command -v pg_restore >/dev/null && \
   [ "$(pg_restore --version | grep -oE '[0-9]+' | head -1)" -ge 16 ] 2>/dev/null; then
  verde "já instalado ($(pg_restore --version | head -1))"
else
  sudo install -d /usr/share/postgresql-common/pgdg
  sudo curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc
  . /etc/os-release
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
    | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq postgresql-client-16
  verde "instalado"
fi

# --- uv --------------------------------------------------------------------

azul "4/6  uv (gerenciador Python do projeto)"
if command -v uv >/dev/null; then
  verde "já instalado ($(uv --version))"
else
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  verde "instalado — abra um shell novo ou rode: export PATH=\$HOME/.local/bin:\$PATH"
fi

# --- Node ------------------------------------------------------------------
#
# O frontend é Next 16 / React 19. Node 22 LTS é o que o Dockerfile.frontend usa.

azul "5/6  Node 22"
if command -v node >/dev/null && [ "$(node -v | grep -oE '[0-9]+' | head -1)" -ge 22 ]; then
  verde "já instalado ($(node -v))"
else
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - >/dev/null
  sudo apt-get install -y -qq nodejs
  verde "instalado ($(node -v))"
fi

# --- Tailscale -------------------------------------------------------------
#
# É o canal de transferência. Sem ele o 02-importar.sh não alcança o VPS.

azul "6/6  Tailscale"
if command -v tailscale >/dev/null; then
  verde "já instalado"
else
  curl -fsSL https://tailscale.com/install.sh | sh
  verde "instalado"
fi

if tailscale status >/dev/null 2>&1; then
  verde "conectado à tailnet"
  if tailscale status 2>/dev/null | grep -q vps-docker03; then
    verde "vps-docker03 visível"
  else
    aviso "vps-docker03 NÃO aparece na tailnet — confira se o VPS está ligado"
  fi
else
  echo
  erro "esta máquina ainda NÃO está na tailnet."
  erro "Rode:  sudo tailscale up"
  erro "e autorize no navegador com a mesma conta do VPS."
  exit 1
fi

echo
azul "Máquina pronta."
echo "Próximo passo:"
echo "  scripts/migrar-dev/02-importar.sh vps-docker03:/tmp/chatnexus-migracao"
