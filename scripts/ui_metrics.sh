#!/usr/bin/env bash
#
# Métricas de dívida de UI do painel — o placar da migração para shadcn/ui.
#
# Cada número aqui é um item do PRD (`docs/benchmark/nosso-painel/` e o plano da
# migração). O ponto não é a foto, é a derivada: nenhum número pode subir. Por
# isso `--check` compara com a linha de base e falha quando algo piora — é o que
# impede o padrão antigo de voltar por um PR distraído (ADR-013).
#
# Uso:
#   scripts/ui_metrics.sh            # imprime a tabela
#   scripts/ui_metrics.sh --save     # grava a linha de base atual
#   scripts/ui_metrics.sh --check    # falha se qualquer métrica subiu
#
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$RAIZ/frontend/src"
APP="$SRC/app"
UI="$SRC/components/ui"
BASELINE="$RAIZ/scripts/ui_metrics.baseline"

MODO="${1:-print}"

# Conta ocorrências de um regex estendido em .tsx, ignorando os primitivos:
# `components/ui/` PODE usar HTML cru e cor — é o único lugar que pode.
fora_de_ui() {
  grep -rEo "$1" "$SRC" --include='*.tsx' 2>/dev/null |
    grep -v "^$UI/" | wc -l | tr -d ' '
}

todo_src() {
  grep -rEo "$1" "$SRC" --include='*.tsx' 2>/dev/null | wc -l | tr -d ' '
}

# --- as métricas -------------------------------------------------------------

# Controles de formulário escritos à mão fora dos primitivos (RF1).
FORM_CRU=$(fora_de_ui '<(input|select|textarea)\b')

# Caixas do navegador no lugar de Dialog/Toast (RF3).
CONFIRM_ALERT=$(todo_src '\b(confirm|alert)\(')

# Overlay à mão em vez de Dialog/Sheet — sem foco preso, sem Escape (RF2).
OVERLAY=$(fora_de_ui 'fixed inset-0')

# Cor fora do sistema de tokens (C1). A lista de paletas é a do Tailwind.
PALETA='(bg|text|border|ring|from|to|via|shadow)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(50|100|200|300|400|500|600|700|800|900|950)'
PALETA_CRUA=$(todo_src "$PALETA")

# Hex literal. Três usos são legítimos e ficam de fora, nomeados — o resto é
# cor fora do sistema de tokens:
#   - paleta que o USUÁRIO escolhe (cor de tag, cor da marca da empresa): é
#     dado, não estilo do painel;
#   - CSS de export em PDF: documento impresso, fora do tema do app;
#   - `layout.tsx`: cálculo de contraste da cor de marca (branco vs quase-preto).
HEX_EXCECOES='tags-admin.tsx|aba-modal.tsx|tag-chip.tsx|agente-editor.tsx|empresa-form.tsx|layout.tsx'
HEX_LITERAL=$(grep -rEn '#[0-9a-fA-F]{6}\b' "$SRC" --include='*.tsx' 2>/dev/null |
  grep -vE "$HEX_EXCECOES" | wc -l | tr -d ' ')

# CSS morto: o arquivo inteiro é lixo enquanto existir (S1 da auditoria).
# Conta CLASSE distinta, não linha de seletor — `.vsa-btn` e `.vsa-btn:hover`
# são a mesma classe.
if [ -f "$SRC/app/vsa-components.css" ]; then
  VSA_MORTO=$(grep -oE '^\.[a-z][a-z0-9-]*' "$SRC/app/vsa-components.css" |
    sort -u | wc -l | tr -d ' ')
else
  VSA_MORTO=0
fi

# `dark:` só vale se alguma coisa aplicar a classe `.dark`. Enquanto ninguém
# aplica, todo utilitário desses é código morto — e o número se zera sozinho
# quando o tema passa a usar classe (ADR-010).
#
# Duas formas contam: o `next-themes` com `attribute="class"` (que é como o
# painel faz hoje) ou alguém mexendo na classe na mão.
APLICA_DARK=$(grep -rE 'attribute=["'"'"']class["'"'"']|classList\.(add|toggle)\(\s*["'"'"']dark' \
  "$SRC" --include='*.ts' --include='*.tsx' 2>/dev/null | wc -l | tr -d ' ')
DARK_UTILS=$(todo_src 'dark:(text|bg|border|ring|hover|from|to|via|placeholder|shadow|divide|outline)-[^"[:space:]]+')
if [ "$APLICA_DARK" -gt 0 ]; then DARK_INERTE=0; else DARK_INERTE="$DARK_UTILS"; fi

# Estado de carregamento honesto (RF4): quantos arquivos usam Skeleton.
SKELETON=$(grep -rl 'components/ui/skeleton' "$SRC" --include='*.tsx' 2>/dev/null | wc -l | tr -d ' ')

# O design system paralelo: constantes de className copiadas arquivo a arquivo.
# Conta a DECLARAÇÃO — matar a constante mata os usos junto.
INPUT_CLS=$(todo_src '(const|let)[[:space:]]+(inputCls|selectCls|labelCls|textareaCls|helpCls)')

# Rota que existe e não é alcançável por link, menu ou redirect nenhum.
#
# Rotas de entrada externa não contam: ninguém as linka de dentro porque quem
# navega até elas é um terceiro (o Google, no caso do callback de OAuth).
ENTRADA_EXTERNA="/connections/oauth-callback /login"

ORFAS=0
ORFAS_LISTA=""
while IFS= read -r page; do
  rota="${page#"$APP"}"
  rota="${rota%/page.tsx}"
  [ -z "$rota" ] && rota="/"
  case "$rota" in *"["*) continue ;; esac          # rota dinâmica: pula
  case " $ENTRADA_EXTERNA " in *" $rota "*) continue ;; esac
  dir="$(dirname "$page")"
  refs=$(grep -rF "\"$rota\"" "$SRC" --include='*.tsx' --include='*.ts' -l 2>/dev/null |
    grep -v "^$dir/" | wc -l | tr -d ' ')
  if [ "$refs" -eq 0 ]; then
    ORFAS=$((ORFAS + 1))
    ORFAS_LISTA="$ORFAS_LISTA $rota"
  fi
done < <(find "$APP" -name page.tsx)

PRIMITIVOS=$(find "$UI" -name '*.tsx' 2>/dev/null | wc -l | tr -d ' ')

# --- saída -------------------------------------------------------------------

METRICAS="form_cru=$FORM_CRU
confirm_alert=$CONFIRM_ALERT
overlay_mao=$OVERLAY
paleta_crua=$PALETA_CRUA
hex_literal=$HEX_LITERAL
vsa_morto=$VSA_MORTO
dark_inerte=$DARK_INERTE
input_cls=$INPUT_CLS
rotas_orfas=$ORFAS"

# Skeleton e primitivos são os únicos que devem SUBIR — ficam fora do --check.
INFO="skeleton_arquivos=$SKELETON
primitivos=$PRIMITIVOS"

if [ "$MODO" = "--save" ]; then
  printf '%s\n' "$METRICAS" > "$BASELINE"
  echo "linha de base gravada em $BASELINE"
  exit 0
fi

printf '%-18s %8s %8s\n' "métrica" "agora" "meta"
printf '%-18s %8s %8s\n' "------------------" "--------" "--------"
printf '%-18s %8s %8s\n' "form_cru" "$FORM_CRU" "0"
printf '%-18s %8s %8s\n' "confirm_alert" "$CONFIRM_ALERT" "0"
printf '%-18s %8s %8s\n' "overlay_mao" "$OVERLAY" "0"
printf '%-18s %8s %8s\n' "paleta_crua" "$PALETA_CRUA" "<30"
printf '%-18s %8s %8s\n' "hex_literal" "$HEX_LITERAL" "0"
printf '%-18s %8s %8s\n' "vsa_morto" "$VSA_MORTO" "0"
printf '%-18s %8s %8s\n' "dark_inerte" "$DARK_INERTE" "0"
printf '%-18s %8s %8s\n' "input_cls" "$INPUT_CLS" "0"
printf '%-18s %8s %8s\n' "rotas_orfas" "$ORFAS" "0"
echo
printf '%-18s %8s %8s\n' "skeleton_arquivos" "$SKELETON" ">=20"
printf '%-18s %8s %8s\n' "primitivos" "$PRIMITIVOS" ">=26"
[ -n "$ORFAS_LISTA" ] && echo && echo "órfãs:$ORFAS_LISTA"

if [ "$MODO" = "--check" ]; then
  if [ ! -f "$BASELINE" ]; then
    echo >&2
    echo "ERRO: sem linha de base. Rode: scripts/ui_metrics.sh --save" >&2
    exit 1
  fi
  piorou=0
  echo
  while IFS='=' read -r nome antes; do
    [ -z "$nome" ] && continue
    agora=$(printf '%s\n' "$METRICAS" | grep "^$nome=" | cut -d= -f2)
    if [ "${agora:-0}" -gt "${antes:-0}" ]; then
      echo "REGRESSÃO: $nome subiu de $antes para $agora" >&2
      piorou=1
    fi
  done < "$BASELINE"
  if [ "$piorou" -eq 1 ]; then
    echo >&2
    echo "Métrica de UI piorou. Ver o contrato em frontend/CONTRIBUTING-UI.md." >&2
    exit 1
  fi
  echo "OK — nenhuma métrica de UI subiu."
fi
