---
title: ADR-009 — shadcn/ui como sistema de design único
type: adr
status: aceito
priority: alta
created: 2026-07-30
updated: 2026-07-31
tags: [adr, frontend, design-system, shadcn]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Produto-Painel
projeto_pai:
relacionados: [PRD-Frontend]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-009 — shadcn/ui como sistema de design único

## Status

Aceito. Fundação entregue na Onda 0 (`3bd7a8f`); adoção em andamento.

## Contexto

O painel tinha **três** sistemas de design convivendo:

1. `src/app/vsa-components.css` — 46 classes (`.vsa-btn`, `.vsa-card`, `.vsa-input`…)
   em 465 linhas. **Zero** referências em `.tsx`. Não era código morto de
   bundler: o arquivo era importado por `globals.css` e as 46 classes estavam no
   CSS servido em produção.
2. Primitivos React em `components/ui/` — existiam e quase ninguém usava:
   `EmptyState` em 3 arquivos contra ~40 textos soltos "Nenhum X"; `Table` em 3
   contra 21 `<table>` na mão; `Skeleton` em 1.
3. O sistema real: copiar a `className` da tela ao lado. Daí 686 decisões de cor
   fora dos tokens e 28 aparências para um campo de texto.

O custo não é o peso do CSS. É que quem abre `vsa-components.css` procurando "o
padrão de botão" encontra uma resposta que não vale.

## Decisão

Adotar **shadcn/ui** como sistema único, sobre Tailwind, e **apagar**
`vsa-components.css`.

shadcn e não uma biblioteca de componentes fechada porque o código dos
primitivos entra no repositório: dá para adicionar variante com nome semântico
sem lutar contra a API de terceiro — que é exatamente o que o C2 exige.

## Consequências

### Positivas
- Um vocabulário só. Variação visual nova vira variante no primitivo.
- 33 primitivos instalados; a métrica `vsa_morto` foi a zero.
- Código de página **compõe** em vez de re-estilizar.

### Negativas
- ~200 arquivos mudam de aparência sem que nenhuma tela seja "migrada" — foi o
  maior risco do programa, e por isso a Onda 0 veio sozinha.
- A adoção não vem de graça: `form_cru=322` e `input_cls=40` seguem abertos.
  Instalar o primitivo é barato; trocar 322 campos, não.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Adotar `vsa-components.css` | Duplicaria o vocabulário em vez de unificar; é CSS puro paralelo ao Tailwind que o código usa |
| Biblioteca fechada (MUI, Mantine) | Reescrita total, e variante nova passa a depender da API de terceiro |
| Só disciplinar o Tailwind, sem primitivos | Já era o estado atual — foi o que produziu as 28 aparências de campo |

## Relacionados

- [[PRD-FRONTEND]] — `docs/PRD-FRONTEND.md`
- Contratos C1 e C2 — `docs/frontend/CONTRATOS-UI.md`
- Auditoria S1 e S2 — `docs/benchmark/nosso-painel/analise-ui-ux.md`
