# Chat Nexus — auditoria de UI/UX do painel

Captura de 2026-07-30 contra produção (`chat.vsanexus.com`), conta superadmin,
empresa "VSA Tecnologia LTDA": **123 imagens** — 53 rotas + 5 telas de detalhe,
em desktop (1440×900) e mobile (390×844), mais 5 no tema obsidian —
por `scripts/capture_painel_screens.py`.

Duas lacunas de cobertura, para não passarem por completude: o detalhe de
conexão não foi capturado porque a linha de `/connections` navega por
`router.push` num botão, não por link com `href` (o que também significa que ela
não abre em nova aba nem tem URL copiável); e o detalhe de conversa caiu em
`/chats/relatorios` por causa do padrão de URL usado na descoberta.

Contraparte de `../plataformas/chatvolt/capture-chatvolt/analise-telas.md`: lá o
alvo era o concorrente e o recorte era funcional. Aqui o alvo somos nós e o
recorte é **o que a tela comunica e quanto custa operá-la**.

> **O que esta captura prova e o que não prova.** Quase todas as telas são de
> uma conta com pouco volume — 2 conexões, 9 agentes, 1 atendimento aberto — o
> que mostra bem os estados vazios e o desperdício de espaço, e mostra **mal** o
> comportamento sob carga. A exceção é `/disparador/contatos`, com **19.647
> contatos reais**: é a única tela desta captura que prova comportamento em
> escala, e é justamente onde aparece o pior problema de lista do painel.
> Achado de código vale para todo mundo; achado de screenshot vale para esta
> conta.

---

## O diagnóstico em uma frase

O painel tem **três sistemas de design sobrepostos** — um em CSS que ninguém
usa, um de componentes React que quase ninguém usa, e o real, que é copiar a
`className` da tela ao lado — e o resultado é um produto que parece diferente
a cada rota sem que ninguém tenha decidido isso.

## O que já está bom (e não deve ser mexido junto)

Auditoria que só lista defeito engana sobre o ponto de partida. O painel acerta:

- **Camada de tokens de verdade** — `vsa-design-tokens.css` com três temas,
  cookie + SSR e script anti-FOUC no `<head>` (`theme-constants.ts:26-36`).
  Capturado no tema obsidian, o painel se comporta: fundo, cartão, borda e texto
  trocam corretamente. O problema não é a ausência de sistema, é a fuga dele.
- **Navegação consciente de permissão** — sidebar e abas filtram por RBAC e o
  grupo cai na primeira rota permitida (`sidebar.tsx:88-96`), em vez de mostrar
  menu que dá 403.
- **`/chats`** — filtro por período, canal, departamento, tag, prioridade e
  status, com export CSV/XLSX. É melhor que o equivalente do Chatvolt.
- **`/onboarding`** — 4 passos, progresso, estado por passo. Bem feito; só está
  desligado (ver U0).
- **Trabalho de `situacao`** — o badge "Com a IA" no card de atendimento veio do
  ciclo anterior e resolveu o problema real de "77 conversas todas 'Aguardando'".
- **White-label por empresa** — logo, nome e cores da empresa no topo do
  sidebar, sem gambiarra de tema.
- **Ícones com rótulo acessível** onde alguém pensou no assunto —
  `ShellToggleButton` tem `aria-label` e `title` que mudam com o estado.

---

# Camada 1 — o que se repete em toda tela

Ordenado por quanto custa deixar como está.

## S1. O sistema de design em CSS é 100% morto

`frontend/src/app/vsa-components.css` define **46 classes** (`.vsa-btn`,
`.vsa-card`, `.vsa-input`, `.vsa-badge`, `.vsa-modal`, `.vsa-spinner`,
`.vsa-status-dot`, …) em 465 linhas. Nenhuma delas é referenciada por um único
`.tsx` do projeto.

Não é código morto de bundler: o arquivo é importado em `globals.css:2` e as 46
classes **estão no CSS servido em produção** — verificado em
`/_next/static/chunks/f20fc9d74ad96643.css` (122 KB), onde todas as 46 aparecem.

O custo real não é o peso, é o que ele significa: alguém escreveu o vocabulário
visual do produto inteiro e a implementação seguiu por outro caminho. Quem abrir
esse arquivo procurando "o padrão de botão" encontra uma resposta que não vale.

## S2. Os primitivos React existem, a adoção não aconteceu

`components/ui/` tem **8 componentes**: `api-error`, `badge`, `button`, `card`,
`empty-state`, `separator`, `skeleton`, `table`. Para 68 páginas.

| primitivo | onde é usado | o que existe em vez dele |
|---|---|---|
| `EmptyState` | **3** arquivos | ~40 textos soltos "Nenhum X" / "Sem dados" |
| `Skeleton` | **1** arquivo (`queue-page-client.tsx`) | 17 arquivos com "Carregando…" em texto |
| `Table` | **3** arquivos | **21** arquivos com `<table>` na mão |
| `ApiError` | 4 arquivos | `alert()` e `<div className="text-red-…">` |

`EmptyState` inclusive documenta o padrão certo no próprio JSDoc — ícone, título,
descrição e CTA para o próximo passo (`empty-state.tsx:8-20`). Três telas
seguem. O resto escreve "Nenhuma aba criada ainda." em `text-sm` e para por aí,
sem dizer como criar uma.

Isto é exatamente o que anotamos sobre o Chatvolt em `/forms` — "construíram e
não deram porta de entrada". A diferença é que lá era uma tela; aqui é a
biblioteca inteira.

## S3. 130 utilitários `dark:` que nunca ligam

`globals.css:7` declara `@custom-variant dark (&:is(.dark *))` — ou seja, `dark:`
só vale dentro de um elemento com **classe** `dark`. Mas o tema do painel é
aplicado por **atributo**: `<html data-theme="light|obsidian|black">`
(`app/layout.tsx:157`, `lib/theme.ts:49`). Nada, em lugar nenhum do código,
adiciona a classe `dark`.

Consequência: **130 utilitários `dark:*` em 30 arquivos são código morto**, e em
**68 casos** eles eram justamente a versão escura de uma cor clara fixa. O que o
autor escreveu e o que o usuário vê:

| escrito | vira no tema obsidian |
|---|---|
| `bg-amber-50 dark:bg-amber-950` (`relatorios/allure/page.tsx:31`) | caixa quase branca no painel escuro |
| `text-emerald-700 dark:text-emerald-300` (`governanca/ia-budget/form.tsx:52`) | verde escuro sobre fundo escuro |
| `bg-amber-50/70 dark:bg-amber-950/30` (`atendimento/atendimento-drawer.tsx:1192`) | bloco claro dentro da conversa |

Dois dos três temas do produto (`obsidian` e `black`) carregam esses defeitos.
O tema `light`, que é o default, é o único onde o erro não aparece — e é por
isso que passou despercebido.

**Verificado em produção, não inferido do fonte.** No CSS servido, as regras
compilam como `.dark\:border-amber-700:is(.dark *)` — 44 regras distintas que
exigem um ancestral com classe `dark`. E, com o tema obsidian ativo em
`/relatorios/allure`, o DOM responde:

```js
{ tema: 'obsidian', elementosComClasseDark: 0, elementosComUtilitarioDark: 3 }
```

Três elementos daquela página carregam utilitários `dark:` e **nenhum elemento
da página tem a classe `dark`** — eles estão renderizando a versão clara dentro
do tema escuro.

**Correção mecânica, uma linha:** trocar o custom-variant por
`@custom-variant dark (&:where([data-theme="obsidian"], [data-theme="black"]) *)`.
Aí os 130 utilitários passam a valer — o que exige revisar as 30 telas de uma
vez, porque elas nunca foram vistas com esse código ativo.

## S4. 686 decisões de cor fora do sistema de tokens

O projeto tem uma camada de tokens séria: `vsa-design-tokens.css` (271 linhas)
com os três temas e uma ponte para os tokens do shadcn em `globals.css:9-118`.
Ela é usada — **2.275** utilitários semânticos (`text-muted-foreground`,
`bg-card`, `border-border`…).

Ao lado dela, **686 utilitários de paleta crua** em **82 arquivos** (45% dos
componentes): `bg-emerald-500` (52×), `text-emerald-300` (35×), `text-amber-400`
(33×), `bg-amber-950` (16×)… mais **31 valores hex literais**.

Os tons escolhidos (`-300`, `-400`) são tons de tema escuro. Como o default é
claro, eles chegam ao usuário com contraste baixo — os chips de "Recursos
avançados" do dashboard (`quota-card.tsx:162`, `text-emerald-300` sobre
`bg-emerald-500/15`) são o caso mais visível.

Referência de escala: no CSS do Chatvolt contamos 285 hex distintos e chamamos
de "ausência de sistema de design". Nós temos sistema — e 686 fugas dele.

## S5. Um campo de texto, 28 aparências

**263 `<input>` em 66 arquivos**, com **28 strings de classe distintas** para o
mesmo conceito. As três mais comuns já discordam entre si:

```
23× flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:ring-1 …
18× flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm          ← sem foco definido
 9× flex h-9  w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm …
```

Quatro alturas (`h-8`, `h-9`, `h-10`, sem altura), três tokens de borda
(`border-input`, `border-border/40`, `border-foreground/10`), dois fundos
(`bg-background`, `bg-transparent`), e o anel de foco presente em umas, ausente
em outras — nas ausentes o usuário vê o anel padrão do navegador, que é outro
desenho. Não existe `components/ui/input.tsx`.

O mesmo vale para `<select>`: **34 arquivos** usam o `<select>` nativo, cujo
dropdown é desenhado pelo sistema operacional. `globals.css:226-252` tem um
comentário longo e um hack global para impedir que a lista saia branca no tema
escuro — o hack é bom, mas ele é a evidência do problema, não a solução.

## S6. Confirmação e feedback com as caixas do navegador

- **`confirm()` em 31 arquivos** — inclusive para ações destrutivas (apagar
  conexão, apagar tag, remover usuário).
- **`alert()` em 14 arquivos** para sucesso e erro.
- **Zero** toasts. Nenhuma biblioteca de notificação no `package.json`.
- Nenhum "desfazer" em lugar nenhum.

O `confirm()` do navegador não aceita tema, não aceita o nome do que vai ser
apagado com destaque, e no mobile aparece como caixa do sistema no topo da tela.
Numa operação com 8 atendentes, "apagar" ser um OK/Cancelar cinza é o caminho
mais curto para o incidente que não dá para reverter.

## S7. Não existe estado de carregamento

Zero `loading.tsx` (o mecanismo nativo do App Router), **um** `<Suspense>` no
projeto inteiro, **um** uso de `Skeleton`. O que existe são 17 telas escrevendo
"Carregando…" e o resto exibindo layout vazio até a resposta chegar.

Em tela com dado remoto — e quase toda tela aqui tem — isso é o vazio e o
"não tem nada" ficarem visualmente idênticos.

## S8. A largura não tem limite

`app-shell.tsx:44` renderiza `<main className="min-h-screen p-6 …">` sem
container. Só **9 das 68 páginas** definem `max-w-*`. Num monitor de 1440px o
formulário de "Novo agente" tem campos de ~1.500px de largura para digitar um
slug de 20 caracteres; num de 2560px, pior.

## S9. Mobile é exceção, não modo

- **37 de 163** arquivos usam qualquer breakpoint (`sm:`/`md:`/`lg:`).
- **13 das 21** tabelas escritas à mão não têm wrapper de scroll horizontal —
  numa viewport de 390px elas empurram a página inteira.

Existe `install-pwa-prompt.tsx`, ou seja, o produto se oferece como app
instalável — o que torna a lacuna mais cara, não menos.

## S10. Emoji como ícone, junto com a biblioteca de ícones

**58 emojis em 31 arquivos** (🧪 8×, ✅ 5×, ⚠ 5×, 🔒 3×, 📷 3×…) convivendo com
lucide-react. Emoji não herda `currentColor`, não escala com o texto do mesmo
jeito e depende da fonte do sistema: no host Linux desta captura, vários
renderizaram como caixa vazia (▯) — inclusive no título "▯ Conexões WhatsApp" e
no card "▯ Cleanup: fila limpa" do dashboard. Em Windows e macOS eles aparecem;
em Linux e em alguns Androids, não.

## S11. Navegação: três camadas, e a terceira corta

Para chegar a uma tela o usuário passa por: **sidebar** (6 grupos) → **abas de
topo** (até 11) → em `/atendimento`, uma **terceira sidebar** interna (5 abas de
sistema + abas do usuário).

O grupo "IA & Conteúdo" tem 11 abas e a barra rola horizontalmente sem nenhuma
affordance — na captura em 1440px a última aba aparece cortada ao meio
("Modelo por ag…") e não há seta, sombra ou fade indicando que há mais.

Além disso:
- **8 rotas não aparecem em nenhuma navegação.** Cinco são alcançáveis por botão
  dentro da tela pai (`/agents/new`, `/menus/new`, `/catalog/models/new`,
  `/catalog/mcp/new`, `/chats/relatorios`) e uma é callback de OAuth. Sobram
  **duas que não são alcançáveis por nada**: `/onboarding` e
  `/atendentes/me/dashboard` — nenhum link, menu ou redirect no código inteiro.
- Não há busca global, atalho de teclado nem breadcrumb — em 62 rotas.

## S12. Microcopy: plural entre parênteses e jargão interno na tela

**50 ocorrências de plural com `(s)`** — "4 perfil(s)", "61 permissão(ões)",
"1 user(s)", "12 contato(s)". Três numa linha só em `/settings/perfis`.
JavaScript resolve plural desde sempre; `(s)` é a marca de string montada por
concatenação.

Junto com isso, jargão interno chega ao usuário final:

- `/settings/perfis`: badge **"system"** e o texto *"equivalente ao role 'admin'
  legacy"* — a dívida técnica da migração de RBAC virou copy de produto.
- `/agents`: subtítulo *"Agentes cadastráveis (DB) + templates do catálogo
  (código)"*.
- `/agents/new`: *"SYSTEM_PROMPT pt-BR com política não-invente"*,
  *"Template sem metadata cadastrada"*.
- `/dashboard/atendimento`: chips de feature flag crus — "disparador",
  "disparador_media", "MCP custom".
- `/agents`, seção "Templates do catálogo": cada card mostra
  *"Código em `agents/catalog/atendimento_router/`"* — caminho de arquivo do
  repositório como descrição de produto — e a ação chama-se "Override prompt".
- Navegação: "Quick Replies", "Feature flags", "Audit log", "IA Budget",
  "MCP Servers" em inglês, ao lado de "Base de Conhecimento" e "Turnos /
  Jornada" em português — e "Grupos (Disp.)" abreviado por falta de espaço.

## S13. Cinco formatos de data e hora

`toLocaleString("pt-BR")` (27×), `toLocaleString()` sem locale (4×),
`toLocaleDateString("pt-BR")` (3×), `toLocaleTimeString("pt-BR", {hour12:false})`
e mais uma variante com fração. Não há helper compartilhado em `lib/`.

O dashboard mostra o mesmo conceito em duas unidades **na mesma tela**: o tile
diz "TEMPO MÉDIO ESPERA 264.3m" e a tabela logo abaixo diz "4h24m".

---

# Camada 2 — uma frase por tela

Mesma régua do teardown do Chatvolt: o que o desenho da tela revela sobre a
decisão de produto por trás dela.

**`/dashboard/atendimento` — Visão Geral**
As quatro barras de "Uso do plano" aparecem 100% preenchidas em verde porque o
plano é ilimitado (`quota-card.tsx:198-200` desenha `w-full` quando o limite é
`null`) — uma barra cheia significa "no limite" em qualquer outro lugar do
mundo, então a tela comunica exatamente o oposto do que quer dizer.

**`/atendimento` — Operação**
Com uma conversa na lista, 65% da largura fica em branco absoluto, porque a
conversa abre em drawer sobre um backdrop escuro (`atendimento-drawer.tsx:321`)
em vez de painel lado a lado — o operador escolhe entre ver a fila **ou** ler a
conversa, nunca os dois, que é a decisão que todo helpdesk (e o Inbox do
Chatvolt) resolve com duas colunas fixas.

**`/agents` — Agentes IA**
O card entrega `temp 0.50 · top_p 0.85 · 3 tools · 1 KBs` e esconde num contorno
cinza que **8 dos 9 agentes estão inativos** — invertemos a prioridade do card do
Chatvolt, que põe o diagnóstico ("Sem base de conhecimento", "Prompt 8594/6k" em
vermelho) na cara e os hiperparâmetros no editor.

**`/agents/new` — Novo agente**
O campo "Template" despeja a documentação dos **quatro** templates de uma vez —
com "Topologia Router + Parallel Agents", "SYSTEM_PROMPT pt-BR com política
não-invente" e um "agendamentos: Template sem metadata cadastrada" que é
mensagem de erro interno virada texto de ajuda — quando bastava mostrar a
descrição do template selecionado.

**`/connections` — Conexões WhatsApp**
Trocar o modo de atendimento (IA ↔ manual) é um `<select>` dentro da linha da
tabela, sem confirmação e sem feedback de gravação, ao lado de quatro ícones sem
rótulo dos quais um é a lixeira: a ação mais consequente do produto tem o mesmo
peso visual que ordenar uma coluna.

**`/chats` — Histórico de Atendimentos**
É a melhor tela do painel — filtro completo, colunas certas, export CSV/Excel,
CSAT na linha — e mesmo aqui o botão "Filtrar" usa o mesmo gradiente
laranja→azul do "Criar agente", igualando em peso visual "aplicar um filtro" e
"criar uma entidade".

**`/onboarding` — primeiro acesso** ⚠️ *rota órfã*
A tela existe e é boa — 4 passos, barra de progresso, estado "feito" por passo,
CTA só no passo pendente — e **ninguém nunca a viu**: `app/page.tsx:15` manda
todo login direto para `/dashboard/atendimento`, e nenhum link, menu ou
middleware aponta para `/onboarding`. É o mesmo diagnóstico que demos ao
`/forms` do Chatvolt ("construíram e não deram porta de entrada"), aplicado à
primeira hora do cliente novo.

**`/agents/[slug]/edit` — editor de agente**
A página tem 3.000px de altura porque lista os 24 documentos da base de
conhecimento inteiros e sem paginação, empurrando para o fim da rolagem o
"Testar busca" — e o campo que de fato define o produto, o system prompt, é uma
textarea de 200px no topo, menor que a área gasta com a lista de arquivos.

**`/disparador/contatos` — a única tela com volume real**
19.647 contatos, 1.000 renderizados de uma vez, **sem busca, sem filtro e sem
paginação** — só um "Carregar mais (18647)" que enfia mais mil linhas no DOM —
e, ao lado, o botão mais perigoso do produto: "Promover todos (8596)", ação em
massa sobre 8.596 registros com o mesmo gradiente de "Criar agente" e, atrás
dele, um `confirm()` do navegador. Para achar um contato específico, o caminho é
clicar "Carregar mais" dezenove vezes.

**`/tags` (mobile) — o custo de não ter wrapper de scroll**
A coluna "Ações" termina fora da viewport de 390px e não há rolagem horizontal:
editar e excluir tag simplesmente **não existem no celular**. É o caso onde a
falta de responsividade deixa de ser estética e vira perda de função — e são 13
tabelas na mesma situação.

**`/agents`, `/connections`, `/atendimento`, `/tags` — o padrão do vazio**
Todas as listas curtas deixam de 60% a 80% da tela em branco com uma marca
d'água gigante ao fundo, sem usar o espaço para o próximo passo (criar, importar,
conectar) — o oposto do que o `EmptyState` do próprio projeto propõe.

---

# Camada 3 — mobile

O painel é responsivo por acidente: o layout não quebra, mas nenhuma tela foi
**desenhada** para 390px.

**Dois hambúrgueres empilhados em `/atendimento`.** Um no topo (sidebar do app) e
outro 150px abaixo, colado no título "Não resolvidas" (sidebar de abas do
atendimento). Mesmo ícone, mesma cor, significados diferentes.

**A barra de abas sangra fora da tela em toda rota.** Em 390px cabem 3,5 abas de
9 ("Atendimentos · Conversas · Clientes · Agendam…"), sem seta, sombra ou
indicador de que existem mais seis.

**Filtro antes de dado.** Em `/chats`, os 9 controles de filtro empilhados
ocupam **uma tela e meia** antes da primeira linha da tabela. Em mobile, filtro
deveria nascer recolhido atrás de um botão.

**Grid irregular.** Os controles de `/atendimento` mantêm larguras de desktop
(`w-auto` num flex que agora quebra linha): "Todos os departamentos" ocupa 55%
da largura, "Todas as prioridades" 47%, e a busca fica estreita a ponto de
truncar o próprio placeholder ("Buscar nome ou protocolo.").

O contexto agrava: existe `install-pwa-prompt.tsx`, ou seja, o produto se
oferece como app instalável, e o app Android nativo (`android/`) consome as
mesmas telas de operação.

---

# Camada 4 — onde o Chatvolt resolve melhor (e onde nós resolvemos)

Recorte só de UI. A comparação funcional está em `../../matriz-paridade.md`.

| tema | Chatvolt | Chat Nexus |
|---|---|---|
| **Inbox** | duas colunas fixas: fila à esquerda, conversa à direita | drawer sobre backdrop — ou a fila, ou a conversa |
| **Card de agente** | diagnóstico primeiro ("Sem base de conhecimento", "Prompt 8594/6k" em vermelho) | hiperparâmetros primeiro (`temp 0.50 · top_p 0.85`); "inativo" em cinza |
| **Onboarding** | não existe — apostam em tutorial embutido em cada tela | existe, pronto, com 4 passos — e **inalcançável** (rota órfã) |
| **Medidor de consumo** | fixo na sidebar, visível em toda tela | só no dashboard, e a barra de plano ilimitado aparece cheia |
| **Densidade da lista** | linha de tabela | card de ~250px de altura por conversa |
| **Sistema de design** | 285 hex distintos, sem tokens | tokens bons e 686 fugas deles |
| **Temas** | um só | três — dois deles com regressões nunca vistas (S3) |
| **Histórico/export** | retenção de 90 dias, sem export nativo | `/chats` com filtro completo + CSV/XLSX — **melhor que o deles** |
| **Governança** | papéis por agente e por base | RBAC granular, turnos, auditoria — **muito além** |

A leitura: **nossa profundidade funcional está à frente e a ergonomia está
atrás**. O Chatvolt tem menos produto e uma superfície mais resolvida.

---

# Backlog priorizado

Mesma régua do `../../backlog-gaps.md`: **Impacto (1–5) ÷ Esforço** (P=1, M=2,
G=3). Ordem mecânica; onde a dependência técnica sobrepõe, o item diz.

## Faixa 1 — fazer agora

### U0. Ligar o `/onboarding` — score 5,0 (impacto 5 ÷ P)
A tela está pronta e custou trabalho; falta um `redirect` condicional em
`app/page.tsx:15` (checklist incompleto → `/onboarding`) e uma entrada de menu
para voltar depois. É o item de melhor razão impacto/esforço da lista inteira:
hoje **todo cliente novo cai no dashboard sem saber que existe um caminho
guiado**, e o caminho existe.

Critério de aceite: empresa criada agora abre em `/onboarding`; empresa com os
4 passos feitos abre no dashboard; o link continua acessível depois.

### U1. Decidir o destino do `dark:` — score 4,0 (impacto 4 ÷ P)
Hoje 130 utilitários não fazem nada e 68 deles eram correção de contraste. São
dois caminhos, e **não fazer nada é escolher o pior**:
- **Ligar**: `@custom-variant dark (&:where([data-theme="obsidian"],[data-theme="black"]) *)`
  em `globals.css:7`. Uma linha — mas exige revisar as 30 telas afetadas, porque
  ninguém nunca as viu com o código ativo.
- **Apagar**: remover os 130 utilitários e resolver contraste só por token.
  Mais trabalho braçal, resultado mais previsível.

Recomendação: ligar, e capturar as 30 telas nos três temas no mesmo dia
(`--tema obsidian` já existe no script de captura).

### U2. Card de agente vira diagnóstico — score 4,0 (impacto 4 ÷ P)
`/agents` esconde que 8 de 9 agentes estão inativos e que um está sem modelo.
Inverter: estado e problema em destaque, `temp`/`top_p` no editor.
Critério de aceite: abrir `/agents` e responder "qual agente está quebrado?" em
menos de 3 segundos, sem clicar.

### U5. Ajuda contextual em `/agents/new` — score 3,0 (impacto 3 ÷ P)
Mostrar só a descrição do template selecionado, e tirar da tela o
"Template sem metadata cadastrada", que é erro interno virado ajuda.

### U6. Container e densidade — score 3,0 (impacto 3 ÷ P)
`max-w-7xl` no `<main>` de `app-shell.tsx:44` e largura própria para formulário
(campo de slug não precisa de 1.500px).

### U3. Confirmação e feedback próprios — score 2,0 (impacto 4 ÷ M)
Substituir `confirm()` (31 arquivos) e `alert()` (14) por um diálogo de
confirmação do design system e um toast. Regra: **ação destrutiva exige o nome
do objeto no diálogo**; ação reversível não pede confirmação, mostra toast com
"desfazer". Entra na Faixa 1 apesar do score porque é pré-requisito de U11 e de
metade da Faixa 2 — nenhuma tela consegue dar feedback decente sem isso.

### U4. Barra de plano ilimitado — score 2,0 (impacto 2 ÷ P)
`quota-card.tsx:198-200`: trocar a barra cheia por traço/ícone de infinito.
Correção de 3 linhas que hoje comunica o oposto do fato.

## Faixa 2 — próximo ciclo

### U7. `/atendimento` em duas colunas — score 1,7 (impacto 5 ÷ G)
Trocar o drawer (`atendimento-drawer.tsx:321`) por painel lado a lado em `lg+`,
mantendo drawer só em mobile. **Score baixo, prioridade alta**: é a tela onde o
operador passa o dia, e o ganho não é estético — é parar de escolher entre ver a
fila e ler a conversa. As 1.508 linhas do drawer é que fazem o esforço ser G.

Junto: prévia da última mensagem no card (já prevista no plano de abas e nunca
feita) e densidade de linha em vez de card de 250px.

### U8. `Input` e `Select` no design system — score 1,5 (impacto 3 ÷ M)
Criar `components/ui/input.tsx` e `select.tsx`, migrar as 28 variantes e os 34
`<select>` nativos. Isso torna o hack de `globals.css:226-252` desnecessário.

### U9. Estados de carregamento — score 1,5 (impacto 3 ÷ M)
`Skeleton` nas 20 listas principais. Hoje "vazio" e "carregando" são a mesma
tela.

### U10. Mobile de verdade nas telas de operação — score 2,0 (impacto 4 ÷ M)
Wrapper de scroll nas 13 tabelas sem ele; filtro recolhido por padrão; resolver
os dois hambúrgueres; abas com indicador de rolagem.

### U18. Busca e paginação nas listas grandes — score 2,0 (impacto 4 ÷ M)
`/disparador/contatos` tem 19.647 linhas e nenhuma forma de procurar. Mínimo:
busca por nome/telefone server-side, paginação real no lugar do "Carregar mais",
e confirmação com digitação do total para "Promover todos (8596)" — ação em
massa irreversível não pode caber num `confirm()`.

### U11. `EmptyState` em toda lista vazia — score 1,5
O componente existe e documenta o padrão; falta usar nas ~40 telas.

## Faixa 3 — higiene

- **U12. Apagar `vsa-components.css`** (46 classes mortas, 465 linhas no bundle).
  Ver "não fazer" abaixo.
- **U13. Emoji → lucide** nos 31 arquivos.
- **U14. Helper único de data/hora** em `lib/` e migrar os 5 formatos.
- **U15. Navegação**: indicador de rolagem nas abas, busca global (⌘K) e destino
  para as 8 rotas órfãs — ou apagá-las.
- **U17. Microcopy**: matar os 50 plurais `(s)`, traduzir os rótulos de
  navegação em inglês e tirar da tela o jargão interno ("role legacy", "system",
  "SYSTEM_PROMPT", nomes crus de feature flag). Barato, e é o que mais denuncia
  produto interno virando produto vendido.
- **U16. Lista da base de conhecimento** com paginação e busca (24 documentos já
  produzem uma página de 3.000px).

---

# Não fazer

- **Não adotar o `vsa-components.css`.** Ele é um segundo sistema de design em
  CSS puro, paralelo ao Tailwind + shadcn que o código realmente usa. Ressuscitar
  as 46 classes duplica o vocabulário em vez de unificar. Apagar é a decisão que
  deixa **um** sistema em pé.
- **Não migrar tudo para shadcn de uma vez.** 184 componentes; a migração em
  bloco vira um PR impossível de revisar. O caminho é primitivo por primitivo,
  começando por `Input`/`Select`, que são os de maior dispersão.
- **Não espalhar o gradiente laranja→azul.** Hoje ele marca tanto "Criar agente"
  quanto "Filtrar" e o "Editar" de cada card da lista — nove gradientes numa tela
  só. Regra: **um** botão gradiente por tela, na ação primária.
- **Não copiar o paywall do Chatvolt** (modal sobre página desfocada). Já
  registrado como padrão de conversão, não de produto.

---

# Como reproduzir

```bash
# cookie de sessão do navegador logado (DevTools → Application → Cookies)
export COOKIE_SESSAO='<__Secure-better-auth.session_token>'

uv run python scripts/capture_painel_screens.py                    # tudo
uv run python scripts/capture_painel_screens.py --grupo operacao    # um grupo
uv run python scripts/capture_painel_screens.py --tema obsidian     # outro tema
```

As imagens vão para `img/`, que é **gitignored** — elas mostram telefone e nome
de cliente real, conteúdo de conversa e o e-mail dos usuários da empresa. Só
este `.md` entra no repositório.

O script pausa 2,5s entre telas porque o middleware de admin corta em 60 req/min
por usuário (`install_admin_rate_limit`); abaixar isso devolve 429 e a captura
vira screenshot de erro.
