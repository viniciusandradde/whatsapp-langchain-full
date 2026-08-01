# Contratos de UI — C1 a C7

Régua de aceite da migração do painel para shadcn/ui. `docs/benchmark/matriz-telas.md`
cita estes contratos como o critério de fechamento de cada onda; este arquivo é
o texto deles.

> **Procedência.** Escritos durante o planejamento da migração, em 2026-07-30, no
> arquivo `~/.claude/plans/vamos-trocar-de-design-cozy-lamport.md`. Esse arquivo
> foi **sobrescrito** pelo plano da migração de ambiente em 31/07, e com ele os
> contratos saíram do disco. Recuperados do transcript da sessão
> (`11a3cb79-e71e-4ebf-9f5d-afd1bfb68f0e.jsonl`) e trazidos para o repositório em
> 2026-07-31 — que é onde deveriam ter nascido. Texto preservado como estava; as
> notas de estado atual estão marcadas como tal.

---

## C1 — Contrato de tokens

- **Fonte única**: `src/app/globals.css` contém `:root` e `.dark` completos,
  gerados no tweakcn. Nenhum outro arquivo define cor.
- **Camada de marca**: `--brand-primary` e `--brand-secondary` são as **únicas**
  variáveis que o white-label injeta em runtime (`layout.tsx`). Os tokens
  shadcn de marca derivam delas por `var()`/`color-mix`, nunca o contrário.
- **Proibido em componente**: `bg-<paleta>-<n>`, hex literal, `rgba()` fixo.
  Exceção única: séries de gráfico, que usam `--chart-1..5`.
- **Cor nova** só entra virando token com nome semântico.
- Verificação: `paleta_crua` em `scripts/ui_metrics.sh`.

## C2 — Contrato de primitivos

Instalar via CLI, na Onda 0: `input`, `textarea`, `label`, `field`, `select`,
`checkbox`, `switch`, `radio-group`, `dialog`, `alert-dialog`, `sheet`,
`dropdown-menu`, `popover`, `tooltip`, `tabs`, `toast`/`sonner`, `command`,
`avatar`, `progress`, `accordion`, `scroll-area`, `sidebar`, `empty`,
`skeleton`, `table`, `separator`.

- Código de página **compõe** primitivos; não os re-estiliza. `className` em
  primitivo só para layout (espaçamento, grid), nunca para cor, borda ou raio.
- Variação visual nova vira **variante no primitivo**, com nome semântico.
- Nada de `inputCls`/`selectCls`: as 40 constantes são apagadas, não migradas.
- `api-error.tsx` sai de `ui/` (tem lógica de negócio: parse de erro Pydantic,
  quota 402, caminho de upgrade) e vira `components/feedback/api-error.tsx`.

## C3 — Contrato de estados de tela

Toda superfície que busca dado implementa os três, sem exceção:

| estado | componente | regra |
|---|---|---|
| carregando | `Skeleton` no formato do conteúdo | nunca texto "Carregando…" |
| vazio | `Empty` (ícone + título + 1 linha + CTA) | o CTA leva ao próximo passo real |
| erro | `ApiError` | mensagem em pt-BR + ação de repetir |

Vazio-por-filtro é diferente de vazio-por-inexistência: o primeiro oferece
limpar o filtro, o segundo oferece criar.

## C4 — Contrato de feedback e confirmação

| situação | mecanismo |
|---|---|
| sucesso de ação assíncrona | `toast` (3–5s) |
| erro recuperável | `toast` destrutivo com ação de repetir |
| erro de formulário | mensagem no campo (`Field`), nunca banner no topo |
| ação destrutiva | `AlertDialog` com o **nome do objeto** no corpo |
| destrutiva em massa (>50 registros) | `AlertDialog` exigindo digitar o total |
| ação reversível | sem confirmação; `toast` com "desfazer" |

`confirm()` e `alert()` são proibidos pelo lint.

## C5 — Contrato de layout e navegação

- **Shell**: `Sidebar` do shadcn, grupos colapsáveis, estado persistido.
- **Container**: `<main>` com `max-w-screen-2xl`; formulário em coluna de no
  máximo `max-w-2xl`.
- **Cabeçalho de página**: um só componente `PageHeader` (título, descrição,
  ações) — antes havia 7 variantes de `<h1>`.
- **Densidade**: lista longa é linha de tabela, não card de 250px.
- **Breakpoints**: toda tela é verificada em 390 / 768 / 1440.
- **⌘K**: busca global de rota + ação, cobrindo as rotas do catálogo.

## C6 — Contrato da thread da inbox

Um tipo `MensagemThread` na fronteira da UI, com a API mapeada para ele num
único adaptador, de modo que o componente de thread não conheça o payload do
backend. É o que permite trocar a renderização sem tocar em endpoint e o que
impede a inbox de virar refém do formato de uma biblioteca de chat.

> **Estado em 2026-07-31:** a Onda 2 entregou as duas colunas e a lista densa
> (`aaa7c63`), mas **o adaptador não foi escrito** — o componente de thread
> ainda lê o payload do backend direto. Contrato em aberto.

## C7 — Contrato de aceite por onda

Uma onda só fecha quando:

1. `make check-web` passa.
2. `scripts/ui_metrics.sh` mostra as métricas da pasta zeradas.
3. O lint da pasta migrada está no modo estrito.
4. As telas foram capturadas nos **dois temas** e em **390px**
   (`scripts/capture_painel_screens.py --grupo <x> --tema dark`).
5. As linhas da onda em `docs/benchmark/matriz-telas.md` estão preenchidas.
6. Nenhum endpoint, payload ou evento SSE mudou.

> **Estado em 2026-07-31:** o item 5 é o que mais escapou — a matriz tem só duas
> telas marcadas `✅ feito`, embora seis ondas tenham commits. Ver
> [PRD-FRONTEND](../PRD-FRONTEND.md), seção "Dívida de aceite".

---

## Numeração de ADR

O plano original numerava seus próprios ADRs (ADR-010 tokens, ADR-012
`assistant-ui`, ADR-013 ESLint, ADR-014 reescrita dos primitivos, ADR-015
matriz). Essa numeração **não é a do repositório** — os ADRs versionados vivem em
`docs/obsidian-vault/03-Resources/ADRs/` e iam até o 008 quando a migração
começou. As decisões do plano foram reescritas na numeração do repositório a
partir do **ADR-009**; quando um commit ou documento antigo citar "ADR-013",
leia como referência ao plano, não ao vault.
