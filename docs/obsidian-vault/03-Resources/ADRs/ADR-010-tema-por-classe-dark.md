---
title: ADR-010 — Tema por classe `.dark` (next-themes), e três temas viram dois
type: adr
status: aceito
priority: alta
created: 2026-07-30
updated: 2026-07-31
tags: [adr, frontend, tema, tokens]
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

# ADR-010 — Tema por classe `.dark` (next-themes), e três temas viram dois

## Status

Aceito. Entregue na Onda 0 (`3bd7a8f`).

## Contexto

O painel tinha três temas (`light`, `obsidian`, `black`) selecionados por
atributo `data-theme` na raiz, com cookie + SSR e script anti-FOUC. A camada de
tokens funcionava: capturado no tema obsidian, fundo, cartão, borda e texto
trocavam corretamente.

O defeito estava em outro lugar. O Tailwind resolve o utilitário `dark:` pelo
`@custom-variant`, que por padrão casa com a **classe** `.dark`. Como o app
aplicava `data-theme` e nunca a classe, os **130 utilitários `dark:`** espalhados
pelo código não faziam absolutamente nada.

E 68 deles eram correção de contraste. Ou seja: alguém escreveu
`bg-amber-50 dark:bg-amber-950`, viu que ficava certo no claro, e o escuro
renderizava a caixa quase branca — em produção, sem ninguém perceber, porque
ninguém nunca viu aquele código ativo.

## Decisão

Trocar `data-theme` pela **classe `.dark`**, via `next-themes`, e **remover o
tema `black`**.

Dois temas e não três porque é o par que os blocos do shadcn suportam sem
adaptação, e porque `obsidian` e `black` diferiam por um degrau de fundo — não
justificavam manter uma terceira coluna de tokens que ninguém revisava.

## Consequências

### Positivas
- Os 130 `dark:` passam a funcionar. Métrica `dark_inerte` foi a zero.
- `next-themes` traz SSR sem flash, dispensando o script anti-FOUC próprio.
- Um degrau a menos de manutenção em cada token novo.

### Negativas
- **Trinta telas passaram a renderizar código que ninguém tinha visto ativo.**
  Ligar os `dark:` é ganho e risco na mesma linha; a mitigação é a captura nos
  dois temas, exigida pelo contrato C7.
- Quem usava `black` perde a opção. Ninguém reclamou — era escolha de 1 usuário.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Apagar os 130 `dark:` e resolver contraste só por token | Mais previsível, mas joga fora 68 correções de contraste que alguém já pensou |
| Manter `data-theme` e reconfigurar o `@custom-variant` | Uma linha resolveria, mas mantém três temas e o script anti-FOUC próprio |
| Não fazer nada | É escolher o pior: 130 utilitários que mentem sobre o que fazem |

## Relacionados

- [[ADR-011-white-label-por-indirecao]] — a indireção que sobreviveu à troca
- Auditoria S3 — `docs/benchmark/nosso-painel/analise-ui-ux.md`
- Contrato C1 — `docs/frontend/CONTRATOS-UI.md`
