# Playbook — migração de um painel para shadcn/ui

> Registro do programa que migrou o painel do Chat Nexus, **e** o método
> destilado para repetir em outro projeto. A Parte I é o caso; as Partes II–VI
> são transportáveis.
>
> **Estado do caso:** Ondas 0–6 em produção desde 2026-08-02 (`master 21337b2`,
> PR #64 — 55 commits, 250 arquivos, 44 telas). Onda 7 não começou.
> **Atualizado:** 2026-08-04.

Para replicar em outro repositório, o mínimo a copiar é:

1. este arquivo,
2. `scripts/ui_metrics.sh` (Apêndice A — está inteiro aqui),
3. `.github/workflows/frontend.yml` (Apêndice B),
4. o esqueleto dos contratos C1–C7 (Parte III).

O resto é adaptação.

---

# Parte I — O caso

## 1. O diagnóstico

O painel tinha **três sistemas de design sobrepostos**, e nenhum deles era o que
o código usava de verdade:

| # | sistema | adoção real |
|---|---|---|
| 1 | `vsa-components.css` — 46 classes, 465 linhas | **zero** referências em `.tsx` |
| 2 | primitivos React em `components/ui/` | `EmptyState` em 3 arquivos, `Table` em 3, `Skeleton` em 1 |
| 3 | copiar a `className` da tela ao lado | **o sistema real** |

O sintoma que o usuário sentia: *o produto parece diferente a cada rota sem que
ninguém tenha decidido isso*.

A auditoria (2026-07-30, sobre capturas de 53 rotas em desktop 1440×900 e mobile
390×844, mais o tema escuro) produziu **13 sintomas (S1–S13)** e **19 itens de
backlog (U0–U18)**. Os quatro mais caros:

| achado | número |
|---|---|
| utilitários `dark:` que nunca ligavam | **130** |
| decisões de cor fora dos tokens | **686** |
| aparências distintas para um campo de texto | **28** (40 constantes `inputCls`/`selectCls` copiadas) |
| `confirm()` / `alert()` do navegador | **31** / **14** arquivos |

O caso do `dark:` merece destaque porque é o padrão do gênero: o Tailwind resolve
`dark:` pela **classe** `.dark`, e o app aplicava `data-theme`. Os 130
utilitários eram código morto — e **68 deles eram correção de contraste**.
Alguém escreveu `bg-amber-50 dark:bg-amber-950`, conferiu no claro, e o escuro
nunca renderizou aquilo. Em produção. Por meses.

## 2. O que foi decidido

Oito ADRs, numerados 009–016 no repositório (`docs/obsidian-vault/03-Resources/ADRs/`):

| ADR | decisão | por quê, em uma linha |
|---|---|---|
| **009** | shadcn/ui como sistema único; `vsa-components.css` apagado | o código dos primitivos entra no repo — variante nova não depende de API de terceiro |
| **010** | tema por classe `.dark` via `next-themes`; 3 temas viram 2 | é o que o `@custom-variant` exige; e o par claro/escuro é o que os blocos do shadcn suportam sem adaptação |
| **011** | white-label por indireção: `--primary: var(--brand-primary)` | colar os tokens crus mata o white-label **sem erro nenhum** |
| **012** | navegação de 3 camadas vira 1, com ⌘K por cima | a barra de abas cortava em "Modelo por ag…" sem indicação de que havia mais 6 destinos |
| **013** | inbox em 2 colunas acima de `lg`, drawer abaixo | com 77 atendimentos abertos, ver a fila **ou** a conversa é escolher entre atender e saber quem espera |
| **014** | `ConfirmDestrutivo` com `tom`; `ButtonLink` no lugar de `<Link><Button>` | vermelho em tudo é vermelho em nada; e `<button>` dentro de `<a>` são dois alvos interativos |
| **015** | aceite por onda **medido**, não opinado | "ficou melhor" não é verificável — e o histórico tem um revert total por causa disso |
| **016** | `SKIP_MIGRATIONS` — processo local nunca migra banco compartilhado | nasceu do incidente I1 (abaixo) |

## 3. O resultado, medido

`bash scripts/ui_metrics.sh`, hoje:

| métrica | agora | meta | |
|---|---:|---:|---|
| `vsa_morto` | **0** | 0 | ✅ |
| `dark_inerte` | **0** | 0 | ✅ |
| `rotas_orfas` | **0** | 0 | ✅ |
| `hex_literal` | **0** | 0 | ✅ |
| `primitivos` | **33** | ≥26 | ✅ |
| `form_cru` | 322 | 0 | 🟡 |
| `confirm_alert` | 65 | 0 | 🟡 |
| `paleta_crua` | 619 | <30 | 🟡 |
| `input_cls` | 40 | 0 | 🟡 |
| `overlay_mao` | 26 | 0 | 🟡 |
| `skeleton_arquivos` | 4 | ≥20 | 🟡 |

**A leitura honesta:** as cinco fechadas são de **fundação** — dependem de uma
decisão e um commit. As seis abertas são de **adoção** — dependem de tocar 322
campos, 65 confirmações, 619 usos de cor, um por um. Instalar o primitivo é
barato; trocar todos os usos, não.

Isso não é fracasso do programa, é a forma da curva. Vale saber disso antes de
prometer prazo.

## 4. A stack final

```
Next 16.1.6 · React 19.2.3 · Tailwind v4 · shadcn 4 (style "base-nova")
@base-ui/react · next-themes · cmdk · sonner · lucide-react
class-variance-authority · tailwind-merge · tw-animate-css
```

`components.json` com `cssVariables: true`, `baseColor: neutral`, `rsc: true`.

---

# Parte II — O método, em oito passos

Esta é a parte replicável. Cada passo tem um **produto** verificável.

## Passo 1 — Auditar antes de tocar em nada

**Produto:** um documento com sintomas numerados (S1…Sn) e backlog priorizado
(U0…Un), cada item com a evidência que o gerou.

Duas fontes, e as duas são necessárias:

**(a) Contagem no código.** Rode isto no repositório-alvo — é o mesmo grep que
virou a régua depois:

```bash
SRC=frontend/src

# campos de formulário fora dos primitivos
grep -rEo '<(input|select|textarea)\b' $SRC --include='*.tsx' | grep -vc "components/ui/"

# cor fora dos tokens
grep -rEoc '(bg|text|border|ring|from|to|via|shadow)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(50|100|200|300|400|500|600|700|800|900|950)' $SRC --include='*.tsx'

# caixas do navegador
grep -rEn '\b(confirm|alert)\(' $SRC --include='*.tsx' --include='*.ts' | wc -l

# constantes de className — o design system paralelo
grep -rEo '(const|let)[[:space:]]+(inputCls|selectCls|labelCls)' $SRC --include='*.tsx' | wc -l

# CSS que ninguém importa de verdade: para cada classe do arquivo, procure uso
grep -oE '^\.[a-z][a-z0-9-]*' $SRC/app/*.css | sort -u | \
  while read -r c; do n=$(grep -rc "${c#.}" $SRC --include='*.tsx' | paste -sd+ | bc); echo "$n $c"; done | sort -n | head
```

**(b) Captura de tela de todas as rotas**, em desktop e mobile, nos temas que
existirem. Contagem acha o que se repete; captura acha o que só se vê olhando
(hierarquia errada, densidade, estado vazio sem saída).

> Automatize a captura com Playwright. Duas armadilhas que custaram tempo:
> o destino do arquivo ser fixo (rodar contra dois ambientes **sobrescreve** o
> primeiro), e o rate limit do painel — 60 req/min por usuário aqui, e cada tela
> dispara várias chamadas. Sem pausa entre telas o resultado é um screenshot de
> erro, que passa despercebido **porque é uma imagem**.

**Anti-padrão:** começar pela biblioteca. "Vamos migrar para shadcn" sem
auditoria produz uma troca de dependência, não uma correção — e ninguém sabe
dizer, depois, se melhorou.

## Passo 2 — Escrever os contratos antes do código

**Produto:** um arquivo com C1…C7 (Parte III), curto, e que responda "isto pode
entrar no PR?" sem discussão.

Contrato não é estilo-guia. É a **régua de aceite**: quando o revisor diz "isso
não pode", o contrato é o que ele aponta. Sem isso, cada PR renegocia tudo.

**Regra de sobrevivência do documento:** escreva no **repositório**, não no
plano da sessão de IA. Os contratos deste caso nasceram num arquivo de plano em
`~/.claude/plans/`, o arquivo foi sobrescrito por outro plano no dia seguinte, e
eles tiveram que ser recuperados do transcript da sessão. Documento que só
existe fora do git não existe.

## Passo 3 — Instalar a régua e ligar a catraca

**Produto:** `scripts/ui_metrics.sh` (Apêndice A) + `ui_metrics.baseline` +
o job de CI (Apêndice B).

O script imprime a tabela; `--save` grava a linha de base; `--check` **falha se
qualquer número subiu**.

O ponto não é a foto, **é a derivada**. A catraca não exige atingir a meta —
exige não retroceder. É o que impede a migração de se desfazer aos poucos, cada
tela nova reintroduzindo cor crua e `confirm()`, sem ninguém notar até o painel
estar de volta ao que era.

Duas regras de operação:

- **Rodar `--check` antes de commitar tela nova.** No PR #64 o gate reprovou por
  código escrito naquele mesmo dia: `paleta_crua` 620→637 e `confirm_alert`
  65→66, tudo de um painel novo.
- **Nunca "consertar" editando o `.baseline`.** Isso é desligar a catraca. O
  `--save` só se usa quando o número **desce** e você quer travar o ganho.

Detalhe de implementação que evita falso positivo: `components/ui/` fica **fora
da contagem** — é o único lugar que pode usar HTML cru e cor. E linha de
comentário não conta como `confirm()`, senão o componente que documenta o que
substitui faz a métrica subir.

## Passo 4 — Onda 0 sozinha

**Produto:** tokens + primitivos instalados + CSS morto apagado. **Nenhuma tela
migrada.**

Este é o passo de maior risco do programa inteiro: ~200 arquivos mudam de
aparência sem que nenhuma tela tenha sido "migrada", porque todos herdam os
tokens novos. Por isso vai **sozinho**, num commit próprio, revisável como "a
fundação trocou" — e não misturado com mudança de tela, onde ninguém consegue
dizer o que causou o quê.

Ordem interna:

1. tokens (`globals.css`) — com a indireção do Passo 5 já aplicada;
2. `shadcn add` dos primitivos que os contratos listam;
3. apagar o sistema morto — **apagar**, não adotar. Dois vocabulários é o
   problema que se está resolvendo.

## Passo 5 — Preservar o que a fundação atropela em silêncio

**Produto:** a lista de invariantes que a troca de tokens pode quebrar **sem
erro nenhum**, cada uma com um teste de aceite manual.

Neste caso a invariante era o **white-label**: cada empresa sobe cor própria,
injetada em runtime como `--brand-primary`. O shadcn espera `--primary`. Colar o
bloco do tweakcn cru define `--primary` com valor literal — e aí:

> o build passa, o lint passa, os testes passam, o painel abre bonito. E
> `layout.tsx` continua injetando `--brand-primary` que **ninguém mais lê**. O
> cliente simplesmente para de ver a cor dele.

A correção é uma linha, e a direção é fixa:

```css
--primary: var(--brand-primary);          /* shadcn deriva da marca */
--primary-foreground: /* neutro */;        /* nunca derivado da cor da empresa */
```

**Corolário, aprendido em campo:** cor de marca pode **tingir superfície**,
nunca **decidir legibilidade**. Uma empresa com secundária branca produzia texto
branco sobre fundo claro no item de menu ativo. Por isso `--accent-foreground` é
neutro.

**Teste de aceite:** trocar a cor de uma empresa pelo painel e ver o sidebar
mudar. É barato, e é o único jeito de flagrar um no-op silencioso.

Generalizando: liste tudo que injeta estilo em runtime (tema por tenant, modo de
alto contraste, densidade configurável) **antes** de colar tokens de terceiro.

## Passo 6 — Fatiar por onda, com aceite por onda

**Produto:** ondas por área do produto, ordenadas por tráfego e dependência.
Uma onda = um conjunto revisável.

O corte que funcionou aqui:

| onda | escopo |
|---|---|
| 0 | fundação (tokens, primitivos, expurgo) |
| 1 | shell e navegação (sidebar, ⌘K, `PageHeader`, container) |
| 2 | operação — a tela de maior tráfego (inbox) |
| 3 | configuração de IA e conteúdo |
| 4 | conectividade e disparo |
| 5 | dashboards |
| 6 | governança (usuários, empresas, billing) |
| 7 | fechamento (lint estrito global, matriz completa, docs) |

O aceite é o contrato C7 — seis condições objetivas, todas verificáveis por
comando ou por arquivo. Ver Parte III.

**O item que mantém o programa reversível é "nenhum endpoint, payload ou evento
mudou".** Se a UI nova não servir, o backend não volta junto. Aqui o programa
inteiro respeitou isso, com duas exceções conscientes e anotadas.

## Passo 7 — Captura por etapa, e parar até o aceite

**Produto:** para cada etapa, as telas tocadas capturadas nos dois temas, lado a
lado com a referência do "antes", enviadas ao dono do produto **antes** de a
etapa seguinte começar.

Isso não é formalidade. O histórico deste repositório tem **seis mudanças
responsivas num PR só que levaram a revert total, inclusive da parte correta**.
Captura por etapa transforma revert em ajuste pontual.

O ciclo, tal como rodou:

1. implementar na branch;
2. `make check-web` (eslint + tsc + build + métricas);
3. **rebuildar o container do frontend** — `restart` não pega edit quando o
   build é `standalone`;
4. capturar **só as rotas tocadas**, nos dois temas;
5. pôr lado a lado com a captura de produção correspondente;
6. mandar ao dono e **parar** até o aceite;
7. preencher a linha da onda na matriz de telas.

**O que a comparação prova e o que não prova:** a conta de desenvolvimento tinha
3 conexões e 1 atendimento aberto. Isso mostra bem estado vazio e desperdício de
espaço, e mostra **mal comportamento sob carga**. A única tela que provou escala
foi a que tinha 19.647 registros reais no dump.

> Achado de código vale para todo mundo. Achado de screenshot vale para a conta
> que gerou o screenshot.

## Passo 8 — Entregar como um evento, com pré-voo

**Produto:** um PR único, revisado tela a tela, com pré-voo somente-leitura
contra o banco real antes do merge.

O roteiro que funcionou para 55 commits de uma vez:

1. **pré-voo somente-leitura** contra o banco de produção — conferir cada
   suposição do release (quantas linhas o backfill toca, se aquele campo é mesmo
   sempre nulo, se aquele template ainda existe);
2. **backup verificado** — não "existe o comando", e sim *rodado e íntegro*;
3. **janela de baixo tráfego**, medida, não chutada;
4. merge;
5. **esperar o container novo ficar healthy** — deploy verde ≠ migration
   aplicada;
6. conferir as invariantes no banco;
7. um teste real ponta a ponta.

O pré-voo desarmou todos os P0 **antes** do deploy. Vale mais que qualquer
checklist escrita na véspera.

Sobre a ferramenta do pré-voo: leitura imposta em **duas camadas** — recusa
local (só `SELECT`/`WITH`, comando único, literais neutralizados antes da
varredura de verbos) **e** `default_transaction_read_only=on` no servidor. As
duas foram testadas mandando uma escrita de propósito antes da primeira consulta
real.

---

# Parte III — Os contratos C1–C7

Texto adaptável. O que está entre colchetes é o que muda por projeto.

### C1 — Tokens

- **Fonte única**: `globals.css` contém `:root` e `.dark` completos. Nenhum
  outro arquivo define cor.
- **Camada de marca**: `[--brand-primary]` e `[--brand-secondary]` são as
  **únicas** variáveis injetadas em runtime. Os tokens do design system derivam
  delas por `var()`/`color-mix`, **nunca o contrário**.
- **Proibido em componente**: `bg-<paleta>-<n>`, hex literal, `rgba()` fixo.
  Exceção única: séries de gráfico (`--chart-1..5`).
- **Cor nova** só entra virando token com nome semântico.
- Verificação: `paleta_crua` e `hex_literal`.

### C2 — Primitivos

- Instalar via CLI, na Onda 0: `input`, `textarea`, `label`, `field`, `select`,
  `checkbox`, `switch`, `radio-group`, `dialog`, `alert-dialog`, `sheet`,
  `dropdown-menu`, `popover`, `tooltip`, `tabs`, `sonner`, `command`, `avatar`,
  `progress`, `accordion`, `scroll-area`, `sidebar`, `empty`, `skeleton`,
  `table`, `separator`.
- Página **compõe** primitivos; não os re-estiliza. `className` em primitivo só
  para layout (espaçamento, grid), nunca para cor, borda ou raio.
- Variação visual nova vira **variante no primitivo**, com nome semântico.
- Nada de `inputCls`/`selectCls`: as constantes são **apagadas**, não migradas.
- Componente com lógica de negócio sai de `ui/` (ex.: parser de erro da API vai
  para `components/feedback/`).

### C3 — Estados de tela

Toda superfície que busca dado implementa os três, sem exceção:

| estado | componente | regra |
|---|---|---|
| carregando | `Skeleton` no formato do conteúdo | nunca texto "Carregando…" |
| vazio | `Empty` (ícone + título + 1 linha + CTA) | o CTA leva ao próximo passo real |
| erro | `ApiError` | mensagem no idioma do produto + ação de repetir |

Vazio-por-filtro ≠ vazio-por-inexistência: o primeiro oferece limpar o filtro, o
segundo oferece criar.

### C4 — Feedback e confirmação

| situação | mecanismo |
|---|---|
| sucesso de ação assíncrona | `toast` (3–5s) |
| erro recuperável | `toast` destrutivo com ação de repetir |
| erro de formulário | mensagem no campo (`Field`), nunca banner no topo |
| ação destrutiva | `AlertDialog` com **o nome do objeto** no corpo |
| destrutiva em massa (>50 registros) | `AlertDialog` exigindo **digitar o total** |
| ação reversível | sem confirmação; `toast` com "desfazer" |

`confirm()` e `alert()` são proibidos pelo lint. A confirmação tem **tom**:
`destrutivo` pinta de vermelho e avisa que não dá para desfazer; `serio` não
pinta (resetar senha, reativar acesso).

### C5 — Layout e navegação

- **Shell**: `Sidebar`, grupos colapsáveis, estado persistido por cookie (o SSR
  já sai com a largura certa e dispensa script anti-flash).
- **Container**: `<main>` com largura máxima; formulário em coluna estreita.
- **Cabeçalho**: um só componente `PageHeader` — antes havia 7 variantes de `<h1>`.
- **Densidade**: lista longa é linha de tabela, não card de 250px.
- **Breakpoints**: toda tela verificada em 390 / 768 / 1440.
- **⌘K**: busca global de rota + ação, lendo **o mesmo catálogo** da sidebar,
  com o mesmo filtro de permissão — nunca oferece destino que devolveria 403.

### C6 — Fronteira de tipo nas telas complexas

Um tipo próprio na fronteira da UI (ex.: `MensagemThread`), com a API mapeada
para ele num **único adaptador**, de modo que o componente não conheça o payload
do backend. É o que permite trocar a renderização sem tocar em endpoint.

> Este foi o contrato **descumprido** aqui. Ver Parte V.

### C7 — Aceite por onda

Uma onda só fecha quando:

1. o gate do frontend passa (lint + tipos + build + métricas);
2. as métricas **da pasta** estão zeradas;
3. o lint da pasta migrada está no modo estrito;
4. as telas foram capturadas nos **dois temas** e em **390px**;
5. as linhas da onda na matriz de telas estão preenchidas;
6. **nenhum endpoint, payload ou evento mudou**.

---

# Parte IV — As armadilhas, com o custo de cada uma

Estas são as que só se aprende fazendo. Valem para qualquer projeto.

### 1. Colar os tokens do gerador crus mata a customização por tenant — em silêncio

Já detalhado no Passo 5. É a falha mais cara do lote porque **não tem sintoma**:
nenhum erro, nenhum teste vermelho, nada no console. Só o cliente parando de ver
a cor dele.

Agravante: um `shadcn add` que sobrescreva `globals.css` **reintroduz o defeito**
meses depois. Deixe a indireção comentada no arquivo, com o motivo.

### 2. `dark:` sem `.dark` é código morto que se acumula por anos

Se o tema não aplica a classe `.dark`, todo utilitário `dark:` é decorativo. E
como ninguém nunca viu aquele código ativo, ligar a classe **põe 30 telas
renderizando algo que nunca foi revisado**. Ganho e risco na mesma linha — a
mitigação é a captura obrigatória nos dois temas.

Métrica que se zera sozinha: `dark_inerte` só conta se ninguém aplica a classe.

### 3. `<Link><Button>` são dois alvos interativos

`<button>` dentro de `<a>`: leitor de tela anuncia os dois. Era o padrão
dominante, em 17 lugares. A correção ingênua (`Button render={<Link/>}`) quebra
com Base UI, que assume `nativeButton` e derruba erro de console. A solução é um
`ButtonLink` que fixa `nativeButton={false}`.

### 4. `AlertDialogAction` herda a cor primária

A confirmação de **apagar** sai na cor da marca, igual ao botão de salvar. Se a
marca for laranja, pior ainda: não distingue nada. Por isso o `tom` do C4.

### 5. Restart não pega edit quando o build é `standalone`

Ciclo de validação inteiro perdido olhando a versão anterior da tela. É
`--build`, sempre.

### 6. A métrica que sobe é quase sempre a de cor com número

`text-emerald-700`, `bg-red-500/10`, `border-amber-500`. O reflexo é escrever
assim; o certo é `success` / `warning` / `destructive`, cada um com
`-foreground`. Bônus de diagnóstico: **cor com número não acompanha o tema** — o
`dark:` escrito à mão ao lado dela é o sintoma.

### 7. Rate limit transforma captura em screenshot de erro

E screenshot de erro passa despercebido **porque é uma imagem**. Pausa entre
telas, e o script avisando quando vê 429.

### 8. Processo local aplicando migration em banco compartilhado

O incidente I1 do programa: um `uvicorn` local, apontado para o banco de
produção, aplicou as migrations pendentes no startup — porque a aplicação roda
`run_migrations` no boot. Ninguém apertou nada.

Se a sua aplicação migra no startup, uma trava tipo `SKIP_MIGRATIONS` não é
luxo. E vale saber: **subir para o repositório remoto pode ser subir para
produção** quando existe deploy automático no push.

### 9. Documento que mora fora do git evapora

Contratos escritos no plano da sessão, plano sobrescrito no dia seguinte,
recuperação a partir do transcript. Escreva no repositório desde o primeiro
rascunho.

---

# Parte V — O que não funcionou

Um playbook que só conta a parte que deu certo é propaganda.

### A matriz de telas ficou por preencher, e isso teve consequência

O contrato C7 exigia a linha da matriz preenchida por onda. Seis ondas tinham
commit e a matriz tinha **duas** telas marcadas como feitas.

A consequência apareceu depois: para escrever o PRD foi preciso **reconstruir o
estado de cada onda lendo o diff**, em vez de ler a matriz. "Onda concluída"
virou afirmação sem evidência — exatamente o que o contrato existia para evitar.

**Lição transportável:** o passo de registro é o primeiro a ser pulado sob
pressão, e é o único cujo custo aparece semanas depois. Se ele não estiver no
mesmo comando do resto (ou no CI), não acontece.

### A métrica global esconde progresso local

`form_cru=322` não distingue a pasta já migrada da que nem começou. O contrato
pede a métrica **da pasta**; o script só reporta o total. Nunca foi corrigido.

Se for repetir, faça o script aceitar um caminho: `ui_metrics.sh frontend/src/app/agents`.

### Uma onda quase não aconteceu, e ninguém percebeu até a auditoria do PRD

A Onda 3 recebeu **+35/−41 linhas**, de um único commit — o do cabeçalho comum.
Estava marcada como "em andamento" no acompanhamento informal.

### O contrato C6 nunca foi escrito em código

As duas colunas da inbox saíram; o adaptador de tipo, não. O componente de
thread ainda lê o payload do backend direto. Contrato aberto até hoje.

**O padrão comum aos quatro:** o que é **verificado por comando** foi feito
(métricas, lint, build, "não mudou endpoint"); o que dependia de **disciplina
humana** (preencher matriz, escrever adaptador) escorregou. Automatize a régua
do que você não quer perder.

---

# Parte VI — Checklist de replicação

Ordem de execução, do zero, em outro projeto.

**Antes de escrever qualquer componente**

- [ ] Rodar as contagens do Passo 1 e anotar os números **datados**.
- [ ] Capturar todas as rotas, desktop + mobile + cada tema.
- [ ] Escrever a auditoria: sintomas numerados + backlog priorizado por
      impacto ÷ esforço.
- [ ] Listar as **invariantes de runtime** que a troca de tokens pode matar em
      silêncio (tema por tenant, contraste, densidade).
- [ ] Escrever C1–C7 **no repositório**.
- [ ] Instalar `ui_metrics.sh`, rodar `--save`, ligar o job de CI com `--check`.

**Onda 0, sozinha**

- [ ] Tokens, **com a indireção da marca já aplicada** e comentada.
- [ ] `shadcn add` dos primitivos do C2.
- [ ] Apagar o sistema de design morto.
- [ ] Teste de aceite do white-label: trocar a cor de um tenant e ver mudar.
- [ ] Captura das telas de maior tráfego nos dois temas — a fundação muda todas.

**Cada onda seguinte**

- [ ] Implementar.
- [ ] `make check-web` (ou equivalente: lint + tipos + build + `--check`).
- [ ] Rebuild do container (não restart).
- [ ] Capturar só as rotas tocadas, nos dois temas.
- [ ] Lado a lado com o "antes"; mandar ao dono; **parar** até o aceite.
- [ ] Preencher a matriz. Sem isso a onda não fechou.

**Entrega**

- [ ] Pré-voo somente-leitura contra o banco real.
- [ ] Backup rodado e verificado.
- [ ] Janela de baixo tráfego medida.
- [ ] PR único; esperar o container **novo** ficar healthy; conferir invariantes;
      teste real ponta a ponta.

---

# Apêndice A — `scripts/ui_metrics.sh`

Transplantável quase sem edição. O que muda por projeto: o caminho de `SRC`, a
lista de exceções de hex, e o nome do CSS morto.

```bash
#!/usr/bin/env bash
#
# Métricas de dívida de UI do painel — o placar da migração para shadcn/ui.
#
# O ponto não é a foto, é a derivada: nenhum número pode subir. Por isso
# `--check` compara com a linha de base e falha quando algo piora.
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

# Controles de formulário escritos à mão fora dos primitivos.
FORM_CRU=$(fora_de_ui '<(input|select|textarea)\b')

# Caixas do navegador no lugar de Dialog/Toast.
#
# Linha de comentário não conta: o componente que SUBSTITUI o `confirm()` cita
# o `confirm()` na própria documentação, e sem esse filtro a substituição fazia
# a métrica subir.
CONFIRM_ALERT=$(grep -rEn '\b(confirm|alert)\(' "$SRC" --include='*.tsx' --include='*.ts' 2>/dev/null |
  grep -vE '^[^:]+:[0-9]+: *(\*|//|/\*)' | wc -l | tr -d ' ')

# Overlay à mão em vez de Dialog/Sheet — sem foco preso, sem Escape.
OVERLAY=$(fora_de_ui 'fixed inset-0')

# Cor fora do sistema de tokens (C1). A lista de paletas é a do Tailwind.
PALETA='(bg|text|border|ring|from|to|via|shadow)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(50|100|200|300|400|500|600|700|800|900|950)'
PALETA_CRUA=$(todo_src "$PALETA")

# Hex literal. Usos legítimos ficam de fora, nomeados — o resto é cor fora do
# sistema: paleta que o USUÁRIO escolhe (cor de tag, cor da marca) é dado, não
# estilo; CSS de export em PDF é documento impresso; e o cálculo de contraste
# da cor de marca no layout.
HEX_EXCECOES='tags-admin.tsx|aba-modal.tsx|tag-chip.tsx|agente-editor.tsx|empresa-form.tsx|layout.tsx'
HEX_LITERAL=$(grep -rEn '#[0-9a-fA-F]{6}\b' "$SRC" --include='*.tsx' 2>/dev/null |
  grep -vE "$HEX_EXCECOES" | wc -l | tr -d ' ')

# CSS morto: o arquivo inteiro é lixo enquanto existir.
# Conta CLASSE distinta, não linha de seletor.
if [ -f "$SRC/app/vsa-components.css" ]; then
  VSA_MORTO=$(grep -oE '^\.[a-z][a-z0-9-]*' "$SRC/app/vsa-components.css" |
    sort -u | wc -l | tr -d ' ')
else
  VSA_MORTO=0
fi

# `dark:` só vale se alguma coisa aplicar a classe `.dark`. Enquanto ninguém
# aplica, todo utilitário desses é código morto — e o número se zera sozinho
# quando o tema passa a usar classe.
APLICA_DARK=$(grep -rE 'attribute=["'"'"']class["'"'"']|classList\.(add|toggle)\(\s*["'"'"']dark' \
  "$SRC" --include='*.ts' --include='*.tsx' 2>/dev/null | wc -l | tr -d ' ')
DARK_UTILS=$(todo_src 'dark:(text|bg|border|ring|hover|from|to|via|placeholder|shadow|divide|outline)-[^"[:space:]]+')
if [ "$APLICA_DARK" -gt 0 ]; then DARK_INERTE=0; else DARK_INERTE="$DARK_UTILS"; fi

# Estado de carregamento honesto: quantos arquivos usam Skeleton.
SKELETON=$(grep -rl 'components/ui/skeleton' "$SRC" --include='*.tsx' 2>/dev/null | wc -l | tr -d ' ')

# O design system paralelo: constantes de className copiadas arquivo a arquivo.
# Conta a DECLARAÇÃO — matar a constante mata os usos junto.
INPUT_CLS=$(todo_src '(const|let)[[:space:]]+(inputCls|selectCls|labelCls|textareaCls|helpCls)')

# Rota que existe e não é alcançável por link, menu ou redirect nenhum.
# Rotas de entrada externa não contam: quem navega até elas é um terceiro.
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
    echo "Métrica de UI piorou. Ver o contrato em docs/frontend/CONTRATOS-UI.md." >&2
    exit 1
  fi
  echo "OK — nenhuma métrica de UI subiu."
fi
```

---

# Apêndice B — o gate de CI

```yaml
name: frontend

on:
  push:
    paths: ["frontend/**", "scripts/ui_metrics.sh", ".github/workflows/frontend.yml"]
  pull_request:
    paths: ["frontend/**", "scripts/ui_metrics.sh", ".github/workflows/frontend.yml"]
  workflow_dispatch: {}

concurrency:
  group: frontend-${{ github.ref }}
  cancel-in-progress: true

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Instalar dependências
        working-directory: frontend
        run: npm ci

      - name: Lint
        working-directory: frontend
        run: npm run lint

      - name: Tipos
        working-directory: frontend
        run: npm run typecheck

      - name: Build
        working-directory: frontend
        env:
          INTERNAL_API_URL: http://api:8000
        run: npm run build

      - name: Métricas de UI (nenhuma pode subir)
        run: bash scripts/ui_metrics.sh --check
```

Duas notas de operação vindas da prática:

- **`paths:` + `cancel-in-progress` juntos escondem mudança.** Se o pipeline de
  deploy filtrar por caminho e cancelar execuções concorrentes, um push pode ver
  seu build cancelado e o seguinte não reconstruir aquele componente — deploy
  verde, mudança não deployada. Ter um caminho de disparo manual que **constrói
  tudo** resolve.
- Este job existia porque, até então, **nada validava o frontend**: a única
  checagem real era o `next build` dentro do docker build do deploy, em arm64
  emulado, depois do push. Erro de tipo aparecia no deploy.

---

# Apêndice C — modelo de ADR

O formato usado aqui, que é o que faz o documento continuar útil um ano depois:

```markdown
# ADR-0NN — <decisão em uma frase, no indicativo>

## Status
Aceito / Proposto / Substituído por ADR-0MM. Onde foi entregue (commit).

## Contexto
O que era verdade antes. **Com número.** "130 utilitários mortos", não
"muitos utilitários mortos".

## Decisão
O que passa a valer, no imperativo. Se houver uma regra de direção
("A deriva de B, nunca o contrário"), ela vem aqui em destaque.

## Consequências
### Positivas
### Negativas   <- esta seção é obrigatória e não pode estar vazia
### Teste de aceite  <- quando a decisão puder falhar em silêncio

## Alternativas consideradas
| opção | por que não |
```

O que faz diferença na prática: a seção de **consequências negativas** e a
**tabela de alternativas**. Sem elas o ADR vira anúncio, e quem chega depois
reabre a discussão do zero porque não sabe o que já foi pesado.

---

# Índice dos documentos do caso

| documento | papel |
|---|---|
| `docs/PRD-FRONTEND.md` | produto: problema, ondas, estado medido, próximos passos |
| `docs/frontend/CONTRATOS-UI.md` | a régua de aceite (C1–C7) |
| `docs/frontend/COMPARACAO-PROD-LOCAL.md` | o método de comparação antes × depois |
| `docs/benchmark/nosso-painel/analise-ui-ux.md` | a auditoria: S1–S13, U0–U18 |
| `docs/benchmark/nosso-painel/defeitos.md` | incidente I1 e achados A1–A11 |
| `docs/benchmark/matriz-telas.md` | comparação tela a tela com o concorrente |
| `docs/obsidian-vault/03-Resources/ADRs/ADR-009…016` | as decisões |
| `scripts/ui_metrics.sh` · `scripts/ui_metrics.baseline` | a régua numérica |
| `scripts/capture_painel_screens.py` | a régua visual |
| `.github/workflows/frontend.yml` | a catraca |

**Nota de numeração:** o plano original da migração numerava os próprios ADRs
(ADR-010 tokens, ADR-013 ESLint, ADR-015 matriz). Essa numeração **não é a do
repositório** — commit ou comentário antigo citando "ADR-013" refere-se ao
plano, não ao vault.
