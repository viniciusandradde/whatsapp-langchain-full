#!/usr/bin/env bash
#
# Monta o pacote de migração do ambiente de desenvolvimento. RODA NO VPS.
#
# Só lê da produção. Nenhum comando aqui altera o banco, os containers ou o
# repositório — a única escrita é em `$SAIDA`. Se algo aqui puder alterar
# produção, é bug.
#
# O que sai daqui:
#   prod.dump          backup íntegro da produção (o primeiro que existe)
#   dev.dump           cópia saneada, sem PII, pra semear o desenvolvimento
#   repo.tar.zst       repositório com .git, sem node_modules/.venv/.next/Baileys
#   claude.tar.zst     histórico, memórias e planos do Claude
#   segredos.tar.zst   .env e frontend/.env.local — SEPARADO de propósito
#   MANIFESTO.txt      tamanho e sha256 de cada peça
#
# Uso:
#   scripts/migrar-dev/00-exportar.sh [diretório de saída]
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SAIDA="${1:-/tmp/chatnexus-migracao}"
CONTAINER_DB="${CONTAINER_DB:-projetos-chatvsanexus-er02mp-db-1}"
BANCO="${BANCO:-whatsapp_langchain}"
# Base temporária onde o saneamento acontece. Nunca é a de produção.
BANCO_ENSAIO="migracao_dev_tmp"

azul()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
verde() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
erro()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*" >&2; }

# --- Guardas ---------------------------------------------------------------

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_DB"; then
  erro "container do banco '$CONTAINER_DB' não está rodando."
  erro "Ajuste com CONTAINER_DB=... $0"
  exit 1
fi

if [ "$BANCO_ENSAIO" = "$BANCO" ]; then
  erro "banco de ensaio não pode ser o de produção."
  exit 1
fi

mkdir -p "$SAIDA"
cd "$RAIZ"

azul "Exportando de $CONTAINER_DB → $SAIDA"
echo

# --- 1. Backup íntegro -----------------------------------------------------
#
# Este arquivo tem duas funções: é a origem do banco de dev e é o backup de
# produção que hoje não existe. Guarde-o.

azul "1/6  Backup íntegro da produção"
docker exec "$CONTAINER_DB" pg_dump -U postgres -Fc "$BANCO" > "$SAIDA/prod.dump"
verde "prod.dump ($(du -h "$SAIDA/prod.dump" | cut -f1)) — contém PII, trate como o banco"

# --- 2. Cópia saneada ------------------------------------------------------

azul "2/6  Saneando uma cópia para desenvolvimento"
docker exec "$CONTAINER_DB" psql -U postgres -q \
  -c "DROP DATABASE IF EXISTS $BANCO_ENSAIO;" \
  -c "CREATE DATABASE $BANCO_ENSAIO;"

docker exec -i "$CONTAINER_DB" pg_restore -U postgres -d "$BANCO_ENSAIO" \
  --no-owner --no-acl < "$SAIDA/prod.dump" >/dev/null 2>&1 || true

docker cp "$RAIZ/scripts/migrar-dev/sanitizar_dev.sql" \
  "$CONTAINER_DB:/tmp/sanitizar_dev.sql"

# ON_ERROR_STOP: o SQL termina com checagens que dão RAISE EXCEPTION se sobrou
# PII. Falhar aqui é o comportamento correto — melhor não exportar do que
# exportar dado de cliente.
if ! docker exec "$CONTAINER_DB" psql -U postgres -d "$BANCO_ENSAIO" \
     -v ON_ERROR_STOP=1 -f /tmp/sanitizar_dev.sql; then
  erro "saneamento FALHOU. Nada foi exportado."
  erro "Provavelmente uma migration criou coluna nova com PII —"
  erro "trate em scripts/migrar-dev/sanitizar_dev.sql e rode de novo."
  docker exec "$CONTAINER_DB" psql -U postgres -q -c "DROP DATABASE IF EXISTS $BANCO_ENSAIO;"
  exit 1
fi

docker exec "$CONTAINER_DB" pg_dump -U postgres -Fc "$BANCO_ENSAIO" > "$SAIDA/dev.dump"
verde "dev.dump ($(du -h "$SAIDA/dev.dump" | cut -f1))"

# --- 3. Caça a dado real no dump saneado -----------------------------------
#
# As checagens dentro do SQL olham coluna por coluna e por isso só pegam o que
# alguém lembrou de listar. Esta varredura olha o dump inteiro, em texto, e é
# ela que pega o que escapou — JID com telefone embutido, `thread_id`, resumo
# escrito pela IA, nome dentro de um JSON de auditoria. Na construção deste
# script ela pegou seis vazamentos que as checagens por coluna não viam.

azul "3/6  Varrendo o dump saneado atrás de dado real"
docker exec "$CONTAINER_DB" pg_dump -U postgres "$BANCO_ENSAIO" \
  > /tmp/dev-plano.sql 2>/dev/null || true

# Telefone brasileiro plausível que NÃO seja o padrão falso (55119...).
VAZOU=0
if grep -aoE '55[1-9][1-9]9[0-9]{8}' /tmp/dev-plano.sql 2>/dev/null \
   | grep -av '^55119' | sort -u | head -5 | grep -q .; then
  erro "telefones que não seguem o padrão falso apareceram no dump:"
  grep -aoE '55[1-9][1-9]9[0-9]{8}' /tmp/dev-plano.sql | grep -av '^55119' \
    | sort -u | head -5 | sed 's/^/      /' >&2
  VAZOU=1
fi

# Termos que identificam clientes reais. Vêm do banco, não são fixos no
# código — assim continuam valendo quando a carteira mudar.
mapfile -t TERMOS < <(
  docker exec "$CONTAINER_DB" psql -U postgres -d "$BANCO" -At -c "
    SELECT DISTINCT palavra FROM (
      SELECT unnest(string_to_array(nome, ' ')) AS palavra FROM empresa
    ) t WHERE length(palavra) >= 6" 2>/dev/null || true
)
for termo in "${TERMOS[@]}"; do
  [ -z "$termo" ] && continue
  n=$(grep -aic -- "$termo" /tmp/dev-plano.sql || true)
  if [ "${n:-0}" -gt 0 ]; then
    echo "      aviso: '$termo' aparece $n vez(es) — nome de empresa é mantido de propósito"
  fi
done

rm -f /tmp/dev-plano.sql
if [ "$VAZOU" -eq 1 ]; then
  erro "abortado: o dump saneado ainda tem telefone real."
  docker exec "$CONTAINER_DB" psql -U postgres -q -c "DROP DATABASE IF EXISTS $BANCO_ENSAIO;"
  exit 1
fi
verde "nenhum telefone real no dump saneado"

docker exec "$CONTAINER_DB" psql -U postgres -q -c "DROP DATABASE IF EXISTS $BANCO_ENSAIO;"

# --- 4. Repositório --------------------------------------------------------
#
# `--exclude` em vez de `git clone` porque os 261 PNGs do benchmark estão no
# .gitignore e o clone não os traria — e eles são a régua da auditoria de UI.

azul "4/6  Empacotando o repositório"
tar --exclude='./node_modules' \
    --exclude='./frontend/node_modules' \
    --exclude='./.venv' \
    --exclude='./frontend/.next' \
    --exclude='./docs/Baileys' \
    --exclude='./htmlcov' \
    --exclude='./.pytest_cache' \
    --exclude='**/__pycache__' \
    --exclude='./.env' \
    --exclude='./frontend/.env.local' \
    -C "$RAIZ" -cf - . \
  | zstd -T0 -3 -q -o "$SAIDA/repo.tar.zst" -f
verde "repo.tar.zst ($(du -h "$SAIDA/repo.tar.zst" | cut -f1)) — sem Baileys, sem segredos"

# --- 5. Estado do Claude ---------------------------------------------------

azul "5/6  Empacotando histórico e memória do Claude"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
if [ -d "$CLAUDE_DIR/projects/-home-dev-projetos-chatnexus" ]; then
  tar -C "$CLAUDE_DIR" -cf - \
      projects/-home-dev-projetos-chatnexus \
      $([ -d "$CLAUDE_DIR/plans" ] && echo plans) \
    | zstd -T0 -3 -q -o "$SAIDA/claude.tar.zst" -f
  verde "claude.tar.zst ($(du -h "$SAIDA/claude.tar.zst" | cut -f1))"
else
  erro "não achei $CLAUDE_DIR/projects/-home-dev-projetos-chatnexus — pulando"
fi

# --- 6. Segredos, separados ------------------------------------------------
#
# Ficam num arquivo próprio de propósito: você olha o que está indo antes de
# mover, e um pacote perdido não leva credencial junto.

azul "6/6  Empacotando segredos (arquivo separado)"
tar -C "$RAIZ" -cf - .env frontend/.env.local 2>/dev/null \
  | zstd -T0 -3 -q -o "$SAIDA/segredos.tar.zst" -f
chmod 600 "$SAIDA/segredos.tar.zst"
verde "segredos.tar.zst — chmod 600, contém OPENROUTER/EVOLUTION/TWILIO/ADMIN"

# --- Manifesto -------------------------------------------------------------

{
  echo "Pacote de migração do ambiente de desenvolvimento — Chat Nexus"
  echo "Gerado em $(date -Is) por $(whoami)@$(hostname)"
  echo "Origem: $CONTAINER_DB / $BANCO"
  echo
  echo "Branch atual: $(git -C "$RAIZ" rev-parse --abbrev-ref HEAD)"
  echo "Commit:       $(git -C "$RAIZ" rev-parse --short HEAD)"
  echo
  printf '%-22s %10s  %s\n' ARQUIVO TAMANHO SHA256
  for f in "$SAIDA"/*.dump "$SAIDA"/*.tar.zst; do
    [ -e "$f" ] || continue
    printf '%-22s %10s  %s\n' \
      "$(basename "$f")" "$(du -h "$f" | cut -f1)" "$(sha256sum "$f" | cut -d' ' -f1)"
  done
  echo
  echo "prod.dump contém PII e é o backup de produção — guarde em local seguro."
  echo "dev.dump foi saneado: sem telefone, documento, conversa ou credencial."
} > "$SAIDA/MANIFESTO.txt"

echo
azul "Pronto."
cat "$SAIDA/MANIFESTO.txt"
echo
echo "Na sua máquina Ubuntu, com Tailscale ligado:"
echo "  scripts/migrar-dev/01-preparar-maquina.sh"
echo "  scripts/migrar-dev/02-importar.sh vps-docker03:$SAIDA"
