---
title: ADR-012 — Navegação de três camadas vira uma, com ⌘K por cima
type: adr
status: aceito
priority: media
created: 2026-07-30
updated: 2026-07-31
tags: [adr, frontend, navegacao, rbac]
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

# ADR-012 — Navegação de três camadas vira uma, com ⌘K por cima

## Status

Aceito. Entregue na Onda 1 (`9fd6695`, `c2e3895`, `002f433`).

## Contexto

O painel navegava em três camadas: sidebar com 6 grupos → barra horizontal de
até 11 abas → e, em `/atendimento`, uma terceira sidebar interna.

A barra de abas **cortava na direita** em "Modelo por ag…" sem seta, sombra ou
qualquer indicação de que havia mais seis destinos. Quem não soubesse que
existiam, não descobria.

Além disso duas rotas eram órfãs — existiam, funcionavam, e nada apontava para
elas: `/onboarding` (4 passos, barra de progresso, tela pronta) e
`/atendentes/me/dashboard`.

## Decisão

Uma camada: cada grupo é uma **seção colapsável da sidebar** com seus destinos
dentro, e o grupo da rota atual abre sozinho. Sobre ela, uma **paleta de comandos
⌘K** com 57 destinos.

A paleta lê o **mesmo `NAV_GROUPS`** da sidebar, com o mesmo filtro de permissão
— nunca oferece destino que devolveria 403. A seção entra no texto buscável, de
modo que digitar "prospecção" encontra Campanhas, Contatos, Grupos e Chaves de
uma vez.

Três regras que vieram do uso:

- **⌘K não é sequestrado dentro de campo de texto.** Em `/atendimento` o
  operador está digitando resposta para o cliente.
- **Um botão "Buscar ⌘K" visível no topo.** Atalho que ninguém descobre não
  existe.
- **Rotas de criação** (`/agents/new` e afins) não entram na sidebar; entram na
  paleta como *ação*, que é o que são.

## Consequências

### Positivas
- Nenhum destino escondido por corte de layout. `rotas_orfas` foi a zero.
- Quem já sabe onde quer chegar faz em duas teclas, em vez de três cliques.
- Estado da sidebar por cookie: o SSR já sai com a largura certa, o que dispensou
  o script anti-flash que existia.

### Negativas
- A sidebar ficou mais alta: 6 grupos × subseções. Mitigado pelo colapso
  automático dos grupos que não são o atual.
- Dois consumidores do mesmo `NAV_GROUPS` (sidebar e paleta) — mudança de rota
  agora precisa estar certa num lugar só, o que é bom, mas o catálogo virou
  código carregado.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Manter as abas e só adicionar indicador de rolagem | Trata o sintoma; a terceira camada em `/atendimento` continuaria |
| Só a paleta ⌘K, sem mexer na sidebar | Atalho é para quem já sabe; não resolve descoberta |
| Menu horizontal único no topo | Não cabe: são ~40 destinos com filtro de permissão |

## Relacionados

- Contrato C5 — `docs/frontend/CONTRATOS-UI.md`
- Auditoria S11 e U15 — `docs/benchmark/nosso-painel/analise-ui-ux.md`
- Achado A6 (dois itens acendendo ao mesmo tempo) — `docs/benchmark/nosso-painel/defeitos.md`
