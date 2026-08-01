---
title: ADR-013 — Inbox em duas colunas acima de `lg`, drawer abaixo
type: adr
status: aceito
priority: alta
created: 2026-07-30
updated: 2026-07-31
tags: [adr, frontend, atendimento, inbox]
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

# ADR-013 — Inbox em duas colunas acima de `lg`, drawer abaixo

## Status

Aceito. Entregue na Onda 2 (`aaa7c63`). O contrato C6 (adaptador da thread)
segue **em aberto**.

## Contexto

A conversa abria num **drawer sobre backdrop escuro**: o operador via a fila
**ou** lia a conversa, nunca as duas. Com 77 atendimentos abertos em produção,
isso é escolher entre atender e saber quem está esperando.

A fila também era grade de **cards de ~250px de altura** — cabiam três ou quatro
conversas na tela.

O Inbox do Chatvolt resolve com duas colunas fixas, e a matriz de telas marcou
essa linha como **"empatar"**: eles resolveram melhor, a onda copia a solução.

## Decisão

Em telas grandes, **fila como coluna fixa à esquerda e conversa à direita**. O
drawer sobrevive abaixo de `lg`, porque 390px não comportam duas colunas.

A fila vira **lista densa**: nome, tempo, situação, não-lidas, prioridade e tags
por linha.

**O que deliberadamente não foi feito:** auto-selecionar a primeira conversa, que
é o padrão de inbox. Abrir uma conversa dispara `marcarAtendimentoLidoAction` —
auto-selecionar marcaria como lida uma conversa que ninguém olhou. O ganho de
ergonomia não paga o dado errado.

## Consequências

### Positivas
- O operador vê a fila enquanto responde.
- Densidade: a lista mostra ordem de grandeza a mais de conversas por tela.
- Emojis do drawer viraram ícone ou texto — "🔒 Nota interna", "⏸ agente pausado"
  renderizavam como caixa vazia em Linux, e emoji não herda `currentColor` nem
  escala com a fonte.

### Negativas
- **A dívida do C6 continua.** O componente de thread ainda lê o payload do
  backend direto, sem o adaptador `MensagemThread`. Enquanto for assim, trocar a
  renderização da conversa exige mexer em quem conhece o formato da API.
- O drawer não foi removido — são dois caminhos de renderização a manter.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Manter o drawer e só reduzir os cards | Não resolve o problema real, que é a exclusão entre fila e conversa |
| Duas colunas em todo breakpoint | 390px não comporta; viraria coluna de 180px ilegível |
| Auto-selecionar a primeira conversa | Marcaria como lida uma conversa não vista |

## Relacionados

- Contrato C6 — `docs/frontend/CONTRATOS-UI.md`
- Matriz, linha `logs` (Inbox) × `/atendimento` — `docs/benchmark/matriz-telas.md`
- Auditoria U7 — `docs/benchmark/nosso-painel/analise-ui-ux.md`
