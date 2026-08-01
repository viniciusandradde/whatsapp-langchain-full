# Comparação produção × local

O painel de produção (`chat.vsanexus.com`) roda a UI **antiga**; o ambiente local
(`10.10.1.105:3100`) roda a UI **em migração**. Este documento é o método para
comparar as duas — que é o critério de aceite de cada etapa, junto do contrato
C7.

## Os dois lados

| | produção | local |
|---|---|---|
| endereço | `https://chat.vsanexus.com` | `http://10.10.1.105:3100` |
| código | `origin/master` | `feat/shadcn-onda-0` |
| UI | pré-shadcn | shadcn |
| dados | cliente real | dump saneado da produção |
| papel | **o antes** — o que o cliente vê hoje | **o depois** — o que vai substituir |

O local não é maquete: é a mesma aplicação, com o mesmo schema e o mesmo formato
de dado, só com telefone e nome embaralhados por LGPD.

## Referência já capturada

`docs/benchmark/nosso-painel/img/` tem **162 imagens de produção**, colhidas em
2026-07-30: 53 rotas + 5 telas de detalhe, em desktop (1440×900) e mobile
(390×844), mais 5 no tema escuro. É a linha de base do "antes" e não precisa ser
recapturada para comparar — só se produção mudar.

A pasta é **gitignored**: mostra telefone e nome de cliente real, conteúdo de
conversa e e-mail dos usuários. Só os `.md` entram no repositório.

## O instrumento

`scripts/capture_painel_screens.py` — 60 rotas em 6 grupos (`visao`, `operacao`,
`ia`, `conectividade`, `governanca`, `observabilidade`).

```bash
uv run python scripts/capture_painel_screens.py \
  --base http://10.10.1.105:3100 \
  --grupo ia \
  --tema dark
```

Flags: `--base` · `--grupo` (repetível) · `--rota` · `--tema` · `--sem-mobile` ·
`--sem-detalhes` · `--cookie` · `--pausa`.

### Autenticação

- **Local**: exporte `ADMIN_EMAIL=admin@dev.local` e
  `ADMIN_PASSWORD=DevNexus2026!` — o script loga sozinho. Sem cookie.
- **Produção**: precisa do cookie de sessão
  (`__Secure-better-auth.session_token`, DevTools → Application → Cookies) em
  `COOKIE_SESSAO` ou `--cookie`. É a **única** peça que depende do dono do
  produto.

### Duas armadilhas do script

1. **`DESTINO` é fixo** (`docs/benchmark/nosso-painel/img`). Rodar contra
   produção e depois contra o local **sobrescreve** o primeiro. Renomeie a pasta
   entre as execuções:

   ```bash
   mv docs/benchmark/nosso-painel/img docs/benchmark/nosso-painel/img-prod
   ```

2. **A pausa de 2,5s entre telas é obrigatória.** O middleware de admin corta em
   60 req/min por usuário; abaixar devolve 429 e a captura vira screenshot de
   erro — que passa despercebido porque *é* uma imagem.

## O fluxo por etapa

Para cada etapa de UI, o ciclo é:

1. Implementar na branch.
2. `make check-web` — eslint + tsc + build + métricas.
3. Rebuildar o container do frontend (`docker compose -p chatnexus-dev up -d
   --build frontend`) — **restart não pega edit**, o build é `standalone`.
4. Capturar **só as rotas tocadas**, nos dois temas.
5. Pôr lado a lado com a imagem correspondente de `img-prod/`.
6. Mandar a captura ao dono do produto e **parar** até o aceite.
7. Preencher a linha da onda em `docs/benchmark/matriz-telas.md`.

O passo 6 não é formalidade. O histórico do repositório tem um caso de seis
mudanças responsivas num PR só que levou a revert total, inclusive da parte
correta. Captura por etapa transforma revert em ajuste pontual.

## O que a comparação prova e o que não prova

A conta local tem pouco volume — 3 conexões, 1 empresa ativa. Isso mostra bem
**estado vazio e desperdício de espaço**, e mostra **mal comportamento sob
carga**. A exceção é `/disparador/contatos`, com 19.647 contatos reais no dump: é
a única tela que prova escala.

Achado de código vale para todo mundo. Achado de screenshot vale para a conta que
gerou o screenshot.

## Quando a UI nova vai para produção

Não vai por etapa. A branch fica local até as ondas fecharem, e a migração é um
PR único, revisado tela a tela contra `img-prod/`. Ver
[PRD-FRONTEND](../PRD-FRONTEND.md), seção 8.

## Relacionados

- [Contratos de UI C1–C7](CONTRATOS-UI.md) — C7 é o aceite por onda
- [Auditoria de UI/UX](../benchmark/nosso-painel/analise-ui-ux.md) — de onde vêm as 162 imagens
- `scripts/ui_metrics.sh` — a régua numérica, complementar à visual
