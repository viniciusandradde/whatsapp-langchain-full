#!/usr/bin/env bash
#
# Expurga `docs/Baileys` da história do git. RODE DEPOIS DA MIGRAÇÃO.
#
# ===========================================================================
# LEIA ANTES DE RODAR
#
# Isto REESCREVE A HISTÓRIA. Todo commit a partir do primeiro que tocou
# Baileys ganha SHA novo. Consequências:
#
#   - `git push` normal passa a ser rejeitado; exige `--force-with-lease`.
#   - Qualquer outra cópia do repositório (outra máquina, CI, colega) fica
#     divergente e precisa re-clonar. Merge da cópia antiga na nova duplica
#     todos os commits.
#   - PR aberto no GitHub aponta pra commits que deixam de existir.
#
# Um dos dois commits envolvidos (9b95c15) JÁ ESTÁ em origin/master. Por isso
# este script não roda sozinho e não faz push — ele para e te mostra o
# comando, para você decidir o momento.
#
# Ganho: ~1,75 GB. O `.git` cai de 1,8 GB para menos de 100 MB.
# ===========================================================================
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CAMINHO_ALVO="docs/Baileys"

azul()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
verde() { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
aviso() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
erro()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*" >&2; }

cd "$RAIZ"

# --- Guardas ---------------------------------------------------------------

if ! command -v git-filter-repo >/dev/null && ! python3 -c "import git_filter_repo" 2>/dev/null; then
  erro "git-filter-repo não encontrado. Instale com:"
  erro "  pipx install git-filter-repo    # ou: uv tool install git-filter-repo"
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  erro "árvore suja. Commite ou guarde tudo antes — o expurgo mexe em todos"
  erro "os refs e não dá pra desfazer com stash."
  git status --short | head -10
  exit 1
fi

azul "Estado atual"
echo "  .git ocupa:  $(du -sh .git | cut -f1)"
echo "  branch:      $(git rev-parse --abbrev-ref HEAD)"
echo "  commits que tocaram $CAMINHO_ALVO:"
git log --all --oneline -- "$CAMINHO_ALVO" | sed 's/^/    /'
echo

# --- Backup do repositório inteiro -----------------------------------------
#
# Um clone espelho antes de reescrever. Se der errado, é daqui que você volta.

ESPELHO="/tmp/chatnexus-antes-do-expurgo-$(date +%Y%m%d-%H%M).git"
azul "1/4  Espelho de segurança"
git clone --mirror . "$ESPELHO" >/dev/null 2>&1
verde "$ESPELHO ($(du -sh "$ESPELHO" | cut -f1))"
aviso "guarde este espelho até confirmar que tudo ficou bem"

# --- Expurgo ---------------------------------------------------------------

azul "2/4  Reescrevendo a história"
aviso "isto vai demorar e vai mudar TODOS os SHAs a partir de 9b95c15"
read -rp "  Continuar? [s/N] " r
[ "$r" = "s" ] || { erro "abortado — nada foi alterado."; exit 1; }

# `--invert-paths` remove o caminho em vez de mantê-lo.
# `--force` porque o repositório não é um clone fresco (o filter-repo recusa
# rodar em repo com remote configurado sem isso).
git filter-repo --path "$CAMINHO_ALVO" --invert-paths --force

azul "3/4  Compactando"
git reflog expire --expire=now --all
git gc --prune=now --aggressive >/dev/null 2>&1
verde ".git agora ocupa $(du -sh .git | cut -f1)"

# --- Conferência -----------------------------------------------------------

azul "4/4  Conferindo"
RESTO=$(git rev-list --objects --all 2>/dev/null | grep -c "$CAMINHO_ALVO" || true)
if [ "$RESTO" -eq 0 ]; then
  verde "nenhum objeto de $CAMINHO_ALVO na história"
else
  erro "ainda restam $RESTO objetos — o expurgo não completou"
  exit 1
fi

# O filter-repo remove o remote de propósito, pra você não fazer push por
# reflexo. Recolocar é decisão consciente.
echo
azul "Pronto. O remote foi REMOVIDO de propósito."
cat <<EOF

  Antes de publicar, confira que o código está íntegro:

    make ci
    cd frontend && npm run lint && npx tsc --noEmit && npm run build

  Só então, e sabendo que ninguém mais tem cópia deste repositório:

    git remote add origin https://github.com/viniciusandradde/whatsapp-langchain-full.git
    git push --force-with-lease --all origin
    git push --force-with-lease --tags origin

  Se algo der errado, o espelho está em:
    $ESPELHO

  Para voltar:
    cd .. && rm -rf chatnexus && git clone $ESPELHO chatnexus

EOF
