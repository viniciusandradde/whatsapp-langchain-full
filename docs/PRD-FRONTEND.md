# PRD — Programa de frontend do Chat Nexus

> Documento de produto do programa que moderniza o painel. Cobre o que foi
> entregue, o que falta e como se mede.
>
> **Estado:** em andamento · **Branch:** `feat/shadcn-onda-0` (local, sem push)
> · **Atualizado:** 2026-07-31

## 1. O problema

O painel tinha **três sistemas de design sobrepostos**: um em CSS que ninguém
usava (`vsa-components.css`, 46 classes, 465 linhas, zero referências), um de
componentes React que quase ninguém usava (`EmptyState` em 3 arquivos, `Table`
em 3, `Skeleton` em 1), e o real — copiar a `className` da tela ao lado.

O resultado é um produto que **parece diferente a cada rota sem que ninguém
tenha decidido isso**. A auditoria de 2026-07-30, sobre 123 capturas de
produção, listou 13 sintomas (S1–S13) e 19 itens de backlog (U0–U18). Os quatro
que mais custavam:

| | evidência na auditoria |
|---|---|
| 130 utilitários `dark:` que nunca ligavam | o `@custom-variant` exigia `.dark` e o app aplicava `data-theme` |
| 686 decisões de cor fora dos tokens | um sistema de tokens bom, e a fuga dele |
| Um campo de texto com 28 aparências | 40 constantes `inputCls`/`selectCls` copiadas entre telas |
| `confirm()` e `alert()` do navegador | 31 e 14 arquivos |

## 2. Objetivo e não-objetivo

**Objetivo.** Um sistema de design só, adotado, com aceite verificável por onda —
sem mudar nenhum endpoint, payload ou evento SSE.

**Não-objetivo.** Redesenhar o produto. A migração troca a implementação visual e
corrige o que a auditoria apontou; **não** inventa telas novas nem muda o modelo
de dados.

## 3. Restrições

- **Compatibilidade de contrato**: nenhuma mudança de API. O backend não é
  tocado pelo programa (as exceções foram duas: busca de contatos server-side, e
  a trava `SKIP_MIGRATIONS` nascida do incidente I1).
- **White-label preservado**: a cor da empresa continua pintando o painel. Colar
  os tokens do tweakcn crus transformaria isso num no-op silencioso — nada
  quebraria no build, o painel só pararia de usar a cor do cliente.
- **Sem deploy até o fim**: a branch fica local; a ida para produção é um PR
  único, revisado tela a tela. Ver `migracao-shadcn-so-localhost` na memória.

## 4. Como se mede

`scripts/ui_metrics.sh` conta o que a auditoria descreveu. É a régua objetiva —
opinião sobre "está mais bonito" não fecha onda.

| métrica | o que conta | 31/07 | meta |
|---|---|---:|---:|
| `vsa_morto` | classes do CSS morto | **0** ✅ | 0 |
| `dark_inerte` | `dark:` que não casa com nada | **0** ✅ | 0 |
| `rotas_orfas` | rotas sem link que leve a elas | **0** ✅ | 0 |
| `hex_literal` | cor crua em componente | **0** ✅ | 0 |
| `primitivos` | primitivos shadcn instalados | **33** ✅ | ≥26 |
| `form_cru` | campos sem primitivo | 322 | 0 |
| `confirm_alert` | caixas do navegador | 65 | 0 |
| `paleta_crua` | `bg-emerald-500` e afins | 620 | <30 |
| `input_cls` | constantes de className | 40 | 0 |
| `overlay_mao` | modal montado à mão | 26 | 0 |
| `skeleton_arquivos` | telas com estado de carregando | 4 | ≥20 |

Cinco metas atingidas, seis abertas. As abertas são de **adoção** — os
primitivos existem, as telas é que ainda não os usam.

## 5. O que cada onda entregou

Ondas definidas por tráfego e dependência. Uma onda = um conjunto revisável.

| onda | escopo | estado | commits |
|---|---|---|---|
| **0** Fundação | tokens, 28 primitivos, expurgo do CSS morto | ✅ completa | `3bd7a8f` |
| **1** Shell e navegação | sidebar colapsável, ⌘K, `PageHeader`, container, `/onboarding` religado | ✅ completa | `9fd6695` `c2e3895` `831d453` `002f433` |
| **2** Atendimento | duas colunas, lista densa, emojis → ícones | 🟡 parcial — falta o adaptador do C6 | `aaa7c63` |
| **3** IA e conteúdo | agents, menus, workflows, catalog | ❌ **quase nada** | só `831d453` (cabeçalho) |
| **4** Conectividade e disparo | campanhas, contatos, busca em 19.647 registros | 🟡 parcial | `cf38eb1` `b8650a9` `685bd3a` |
| **5** Dashboards | barra de plano, donut, formato de data | 🟡 parcial | `6d5ec1c` |
| **6** Governança | usuários, empresas, billing, catálogo de modelos | 🟡 parcial | `36f3a11` `26854b1` `17c3863` `3a4c2d9` |
| **7** Fechamento | lint estrito global, matriz completa | ❌ não começou | — |

**A Onda 3 é a lacuna real.** `app/agents` recebeu **+35/−41 linhas**, de um
único commit, o do `PageHeader`. Os itens U2 (card de agente vira diagnóstico) e
U5 (ajuda contextual em `/agents/new`) seguem intocados.

## 6. Backlog da auditoria — estado medido

Medido no código da branch em 31/07, não copiado da auditoria.

| item | auditoria 30/07 | branch 31/07 | |
|---|---|---|---|
| U0 `/onboarding` órfão | inalcançável | religado, e no menu | ✅ |
| U1 `dark:` inerte | 130 utilitários mortos | `.dark` via next-themes | ✅ |
| U4 barra de plano ilimitado | barra cheia | traço/infinito | ✅ |
| U6 container e densidade | sem largura máxima | `max-w` no `<main>` | ✅ |
| U7 atendimento em 2 colunas | drawer sobre backdrop | colunas em `lg+` | ✅ |
| U12 `vsa-components.css` | 465 linhas mortas | apagado | ✅ |
| U15 ⌘K e rotas órfãs | não existia | 57 destinos, 0 órfãs | ✅ |
| U18 busca em 19.647 contatos | não existia | server-side | ✅ |
| U3 `confirm()`/`alert()` | 31 / 14 arquivos | 27 / 12 | 🟡 |
| U8 `Input`/`Select` | 28 variantes, 34 nativos | primitivos prontos, 30 nativos restam | 🟡 |
| U9 `Skeleton` | 1 arquivo | 5 | 🟡 |
| U11 `EmptyState` | 3 arquivos | 6 | 🟡 |
| U13 emoji como ícone | 31 arquivos | 24 | 🟡 |
| U14 formato de data | 5 formatos | `lib/formato.ts` em 11 arquivos | 🟡 |
| U17 microcopy | jargão interno na tela | rótulos traduzidos | 🟡 |
| **U2** card de agente | hiperparâmetro primeiro | **inalterado** | ❌ |
| **U5** ajuda em `/agents/new` | erro interno como ajuda | **inalterado** | ❌ |
| U10 mobile de verdade | 13 tabelas sem scroll | não medido | ❌ |
| U16 lista da base de conhecimento | 24 docs em página de 3.000px | não tocado | ❌ |

## 7. Dívida de aceite

O contrato C7 exige que a matriz de telas seja preenchida antes de a onda
fechar. Hoje `docs/benchmark/matriz-telas.md` tem **duas** telas marcadas
`✅ feito` — e seis ondas têm commit. A dívida não é cosmética: sem a matriz
preenchida, "onda concluída" vira afirmação sem evidência, que é exatamente o
que este PRD teve de refazer à mão.

**Regra a partir daqui:** nenhuma etapa fecha sem (a) a linha na matriz, (b) a
captura nos dois temas, (c) `ui_metrics.sh` da pasta zerado.

## 8. Próximas etapas, em ordem

1. **Onda 3 — IA e conteúdo.** É a única onda praticamente intocada e concentra
   as duas telas que o cliente novo vê primeiro ao configurar o produto. Começa
   por U2 (card de agente vira diagnóstico: hoje `/agents` esconde que 8 de 9
   agentes estão inativos) e U5.
2. **Fechar o C6** — o adaptador da thread da inbox, dívida da Onda 2.
3. **Adoção dos primitivos** — as seis métricas abertas são todas disso.
   `input_cls` (40 constantes) e `confirm_alert` (65) são as de maior alcance.
4. **Onda 7 — fechamento**: lint estrito, matriz completa, `CLAUDE.md` e
   `ARCHITECTURE.md` atualizados.
5. **PR único para produção**, revisado tela a tela contra as capturas de
   referência. Ver [COMPARACAO-PROD-LOCAL](frontend/COMPARACAO-PROD-LOCAL.md).

## 9. Fora de escopo, com motivo

- **Não ressuscitar `vsa-components.css`.** Era um segundo sistema de design em
  CSS puro, paralelo ao Tailwind + shadcn que o código usa de verdade. Apagar
  deixa **um** vocabulário em pé; adotar duplicaria.
- **Não migrar 184 componentes de uma vez.** Vira PR impossível de revisar. O
  caminho é primitivo por primitivo, começando pelos de maior dispersão.
- **Não espalhar o gradiente laranja→azul.** Um botão gradiente por tela, na
  ação primária. Hoje há telas com nove.
- **Não copiar o paywall do Chatvolt** (modal sobre página desfocada). É padrão
  de conversão, não de produto.

## 10. Documentos relacionados

- [Contratos de UI C1–C7](frontend/CONTRATOS-UI.md) — a régua de aceite
- [Comparação produção × local](frontend/COMPARACAO-PROD-LOCAL.md) — o método
- [Auditoria de UI/UX](benchmark/nosso-painel/analise-ui-ux.md) — S1–S13, U0–U18
- [Matriz de telas](benchmark/matriz-telas.md) — 32 telas × Chatvolt
- [Defeitos da migração](benchmark/nosso-painel/defeitos.md) — I1 + A1–A11
- ADRs **009–016** em `docs/obsidian-vault/03-Resources/ADRs/`
