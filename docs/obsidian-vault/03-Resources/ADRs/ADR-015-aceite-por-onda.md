---
title: ADR-015 — Aceite por onda medido, não opinado
type: adr
status: aceito
priority: alta
created: 2026-07-30
updated: 2026-07-31
tags: [adr, frontend, processo, qualidade]
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

# ADR-015 — Aceite por onda medido, não opinado

## Status

Aceito, e **descumprido em parte** — ver Consequências.

## Contexto

Uma migração visual de ~200 arquivos não tem critério natural de "pronto".
"Ficou melhor" não é verificável, e o histórico deste repositório mostra o custo
de confiar nisso: seis mudanças responsivas num único PR levaram a **revert
total, inclusive da parte que estava certa**.

A migração é fatiada em ondas por área do produto. Sem régua, "onda concluída"
vira afirmação sem evidência.

## Decisão

Uma onda só fecha com **seis condições objetivas** (contrato C7):

1. `make check-web` passa (eslint + tsc + build + métricas).
2. `scripts/ui_metrics.sh` mostra as métricas da pasta zeradas.
3. O lint da pasta migrada está em modo estrito.
4. As telas foram capturadas nos **dois temas** e em **390px**.
5. As linhas da onda em `docs/benchmark/matriz-telas.md` estão preenchidas.
6. Nenhum endpoint, payload ou evento SSE mudou.

O item 6 é o que mantém o programa reversível: se a UI nova não servir, o
backend não precisa voltar junto.

`scripts/ui_metrics.sh` conta o que a auditoria descreveu — `form_cru`,
`confirm_alert`, `paleta_crua`, `input_cls`, `overlay_mao`, `dark_inerte`,
`vsa_morto`, `rotas_orfas`, `skeleton_arquivos`, `primitivos` — contra
`scripts/ui_metrics.baseline`.

## Consequências

### Positivas
- Cinco métricas chegaram a zero e isso é **demonstrável**, não opinião.
- O item 6 foi respeitado: o programa inteiro não mudou contrato de API.

### Negativas
- **O item 5 foi o mais descumprido.** Em 31/07 a matriz tem duas telas marcadas
  `✅ feito` e seis ondas têm commit. A consequência apareceu na prática: para
  escrever o PRD foi preciso reconstruir o estado de cada onda **lendo o diff**,
  em vez de ler a matriz.
- Métrica global esconde progresso local: `form_cru=322` não distingue a pasta
  migrada da que nem começou. O contrato pede a métrica **da pasta**, e o script
  hoje só reporta o total.

### Correção adotada

Nenhuma etapa fecha sem (a) a linha na matriz, (b) a captura nos dois temas,
(c) `ui_metrics.sh` da pasta zerado. E toda mudança de UI vai ao dono do produto
**com captura de tela** antes de a etapa seguinte começar.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Revisão visual livre por onda | É o que gerou o revert total do histórico |
| Teste de regressão visual automatizado (Percy e afins) | Custo de infra e de manutenção de baseline alto demais para o tamanho do time |
| Só `make check-web` | Verifica que compila, não que ficou certo |

## Relacionados

- Contrato C7 — `docs/frontend/CONTRATOS-UI.md`
- [[PRD-FRONTEND]], seção "Dívida de aceite" — `docs/PRD-FRONTEND.md`
- `scripts/ui_metrics.sh` · `scripts/capture_painel_screens.py`
