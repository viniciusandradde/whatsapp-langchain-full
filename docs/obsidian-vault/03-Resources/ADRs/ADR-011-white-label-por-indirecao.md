---
title: ADR-011 — White-label por indireção — `--primary` deriva de `--brand-primary`
type: adr
status: aceito
priority: alta
created: 2026-07-30
updated: 2026-07-31
tags: [adr, frontend, white-label, tokens, multi-tenant]
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

# ADR-011 — White-label por indireção: `--primary` deriva de `--brand-primary`

## Status

Aceito. Preservado deliberadamente na Onda 0 (`3bd7a8f`).

## Contexto

Desde a migration 115, cada empresa sobe logo, nome de marca e **cores
próprias**. As cores viram CSS vars `--brand-primary` / `--brand-secondary`,
injetadas em runtime num `<style>` no `<head>` por `layout.tsx`, resolvendo a
empresa ativa pelo cookie.

O shadcn, por sua vez, espera tokens `--primary`, `--secondary` e afins. A forma
natural de instalar o tema — colar o bloco gerado no tweakcn — define
`--primary` com um valor **literal**.

Aí está a armadilha: colar o bloco cru **não quebra nada visível**. O build
passa, o lint passa, os testes passam, o painel abre bonito. O que acontece é
que `layout.tsx` continua injetando `--brand-primary` e ninguém mais lê essa
variável. O white-label vira **no-op silencioso** — o cliente simplesmente para
de ver a cor dele, e o defeito só aparece quando alguém repara.

## Decisão

O bloco de tokens do shadcn **não é colado cru**. Os tokens de marca derivam da
camada de marca:

```css
--primary: var(--brand-primary);
--primary-foreground: /* neutro, nunca derivado da cor da empresa */;
```

A direção é fixa e vale como regra: **os tokens shadcn derivam de
`--brand-primary`/`--brand-secondary`, nunca o contrário.**

Corolário aprendido na prática (achado A5): cor de marca pode **tingir
superfície**, nunca **decidir legibilidade**. Uma empresa com `cor_secundaria`
branca produzia texto branco sobre fundo claro no item de menu ativo. Por isso
`--accent-foreground` e `--sidebar-accent-foreground` são neutros.

## Consequências

### Positivas
- White-label sobrevive à migração. Verificado em runtime: com a empresa ativa,
  `--primary` resolve para `#ff8800`, que é a cor no banco.
- Trocar `cor_primaria` de uma empresa continua repintando o painel inteiro.

### Negativas
- Atualizar tokens pelo tweakcn deixa de ser copiar e colar: exige reaplicar a
  indireção nas linhas de marca. É trabalho manual recorrente.
- Um `shadcn add` que sobrescreva `globals.css` reintroduz o defeito em silêncio.

### Teste de aceite

Trocar `cor_primaria` de uma empresa pelo painel e ver o sidebar mudar. É barato
e é o único jeito de flagrar o no-op.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Colar os tokens do tweakcn crus | Mata o white-label sem erro nenhum — o pior tipo de falha |
| Injetar `--primary` direto em `layout.tsx` | Acopla o runtime ao vocabulário do shadcn; perde a camada de marca como conceito |
| Gerar CSS por empresa em build | Não existe build por empresa; a empresa ativa muda por cookie, em runtime |

## Relacionados

- [[ADR-010-tema-por-classe-dark]]
- Contrato C1 — `docs/frontend/CONTRATOS-UI.md`
- Achado A5 — `docs/benchmark/nosso-painel/defeitos.md`
